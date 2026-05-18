import io
import os
import warnings

import numpy as np
import pandas as pd
import requests
import streamlit as st
from auth import logout, require_auth
from ortools.constraint_solver import routing_enums_pb2, pywrapcp

warnings.filterwarnings("ignore")

API_KEY = os.environ.get("GOOGLE_APIKEY", "")


def get_data_location_input():
    with st.form("Get Location Data & Config File", clear_on_submit=True):
        uploaded_file = st.file_uploader("Upload Excel Template file", type="xlsx")
        submitted = st.form_submit_button("Submit")
        if submitted:
            if uploaded_file is not None:
                df = pd.read_excel(uploaded_file, sheet_name=None)
                try:
                    df_location = df["DATA"]
                    df_config = df["CONFIG"]
                    df_depot = df["DEPOT"]

                    depot = df_depot.set_index("VAR").to_dict("index")
                    config = df_config.set_index("VAR").to_dict("index")

                    depot_address = {
                        "Address": depot["Address"]["VALUE"],
                        "Latitude": depot["Latitude"]["VALUE"],
                        "Longitude": depot["Longitude"]["VALUE"],
                    }

                    df_location = df_location.append(depot_address, ignore_index=True)
                    old_columns = list(df_location.columns)
                    df_location.columns = [col.lower() for col in df_location.columns]

                    st.write(df_location)
                    if {"latitude", "longitude"}.issubset(set(df_location.columns)):
                        st.map(df_location)

                    df_location.columns = old_columns

                    return df_location, config
                except Exception as ex:
                    st.exception(ex)
                    st.stop()
            else:
                st.warning("Please upload a file")
                st.stop()
    return None, None


def calculate_google_map_distance(df_location):
    df_location = df_location.copy()
    df_location["ID"] = df_location.index
    df_location["KEY"] = df_location["Latitude"].astype(str) + "," + df_location["Longitude"].astype(str)

    split_rate = df_location.shape[0] / 10
    if split_rate - int(split_rate) > 0:
        split_rate = int(split_rate) + 1

    df_location_split = np.array_split(df_location, split_rate)
    id_dict = df_location[["ID", "KEY"]].set_index("KEY").to_dict()["ID"]

    distance_matrix_dict = {}
    time_matrix_dict = {}

    for arr1 in df_location_split:
        for arr2 in df_location_split:
            origins = "|".join(arr1["KEY"].values)
            destinations = "|".join(arr2["KEY"].values)

            url = f"https://maps.googleapis.com/maps/api/distancematrix/json?"
            url += f"origins={origins}&destinations={destinations}"
            url += f"&units=metric&key={API_KEY}"

            response = requests.get(url).json()
            response["origin_addresses"] = arr1["KEY"].values
            response["destination_addresses"] = arr2["KEY"].values
            data = response.get("rows", [])

            for id_source, source in enumerate(data):
                for id_dest, dest in enumerate(source.get("elements", [])):
                    key_source = response["origin_addresses"][id_source]
                    key_dest = response["destination_addresses"][id_dest]
                    distance_matrix_dict.setdefault(key_source, {})[key_dest] = dest.get("distance", {}).get("value", 0)
                    time_matrix_dict.setdefault(key_source, {})[key_dest] = dest.get("duration", {}).get("value", 0)

    return {
        "distance_matrix": distance_matrix_dict,
        "time_matrix": time_matrix_dict,
        "gps_data": df_location,
        "id_dict": id_dict,
    }


def calculate_google_or_tools(data, config):
    VEHICLE_NUMBER = int(config["VEHICLE_NUMBER"]["VALUE"])
    MAX_DROP_POINTS = int(config["MAX_DROP_POINTS"]["VALUE"])
    MAX_HOUR_TRIP = float(config["MAX_HOUR_TRIP"]["VALUE"]) * 60 * 60
    MAX_WAITING = float(config["MAX_WAITING"]["VALUE"]) * 60
    MAX_RUNNING_TIME = float(config["MAX_RUNNING_TIME"]["VALUE"]) * 60
    MAX_PENALTY_TIME = float(config["MAX_PENALTY_TIME"]["VALUE"]) * 60

    gps_data = data["gps_data"]
    time_matrix = data["time_matrix"]
    distance_matrix = data["distance_matrix"]
    id_dict = data["id_dict"]
    id_gps = gps_data[["ID", "KEY"]].set_index("ID").to_dict()["KEY"]
    id_address = gps_data[["Address", "ID"]].set_index("ID").to_dict()["Address"]

    distance_matrix_arr = [[0] * len(id_dict) for _ in range(len(id_dict))]
    time_matrix_arr = [[0] * len(id_dict) for _ in range(len(id_dict))]

    INDEX_OF_DEPOT = len(time_matrix) - 1

    def transform_dict_matrix(matrix_dict, matrix_arr):
        for key_source, dests in matrix_dict.items():
            for key_dest, value in dests.items():
                id_source = id_dict[key_source]
                id_dest = id_dict[key_dest]
                matrix_arr[id_source][id_dest] = value
        return matrix_arr

    distance_matrix_arr = transform_dict_matrix(distance_matrix, distance_matrix_arr)
    time_matrix_arr = transform_dict_matrix(time_matrix, time_matrix_arr)

    def create_data_model():
        data_model = {}
        data_model["time_matrix"] = time_matrix_arr
        data_model["time_windows"] = [(0, MAX_HOUR_TRIP) for _ in range(len(time_matrix_arr))]
        data_model["num_vehicles"] = VEHICLE_NUMBER
        data_model["demands"] = [1 for _ in range(len(time_matrix_arr))]
        data_model["vehicle_capacities"] = [MAX_DROP_POINTS for _ in range(VEHICLE_NUMBER)]
        data_model["depot"] = INDEX_OF_DEPOT

        for i in range(len(time_matrix_arr)):
            for j in range(len(time_matrix_arr[i])):
                if time_matrix_arr[i][j] != 0 and j != data_model["depot"]:
                    time_matrix_arr[i][j] = time_matrix_arr[i][j] + MAX_WAITING

        return data_model

    def print_solution(data, manager, routing, solution):
        time_dimension = routing.GetDimensionOrDie("Time")
        result_arr = []

        for vehicle_id in range(data["num_vehicles"]):
            result_obj = {
                "Vehicle": vehicle_id,
                "Routes": [],
                "CumTime": [],
            }
            index = routing.Start(vehicle_id)

            while not routing.IsEnd(index):
                time_var = time_dimension.CumulVar(index)
                result_obj["Routes"].append(manager.IndexToNode(index))
                result_obj["CumTime"].append(solution.Min(time_var))
                index = solution.Value(routing.NextVar(index))

            time_var = time_dimension.CumulVar(index)
            result_obj["Routes"].append(manager.IndexToNode(index))
            result_obj["CumTime"].append(solution.Min(time_var))
            result_arr.append(result_obj)

        return result_arr

    def main_ortools():
        data_model = create_data_model()

        manager = pywrapcp.RoutingIndexManager(
            len(data_model["time_matrix"]), data_model["num_vehicles"], data_model["depot"]
        )
        routing = pywrapcp.RoutingModel(manager)

        def time_callback(from_index, to_index):
            from_node = manager.IndexToNode(from_index)
            to_node = manager.IndexToNode(to_index)
            return data_model["time_matrix"][from_node][to_node]

        transit_callback_index = routing.RegisterTransitCallback(time_callback)
        routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index)

        def demand_callback(from_index):
            from_node = manager.IndexToNode(from_index)
            return data_model["demands"][from_node]

        demand_callback_index = routing.RegisterUnaryTransitCallback(demand_callback)
        routing.AddDimensionWithVehicleCapacity(
            demand_callback_index,
            0,
            data_model["vehicle_capacities"],
            True,
            "Capacity",
        )

        time = "Time"
        routing.AddDimension(
            transit_callback_index,
            MAX_WAITING,
            MAX_HOUR_TRIP,
            False,
            time,
        )
        time_dimension = routing.GetDimensionOrDie(time)

        for location_idx, time_window in enumerate(data_model["time_windows"]):
            if location_idx == data_model["depot"]:
                continue
            index = manager.NodeToIndex(location_idx)
            time_dimension.CumulVar(index).SetRange(time_window[0], time_window[1])

        depot_idx = data_model["depot"]
        for vehicle_id in range(data_model["num_vehicles"]):
            index = routing.Start(vehicle_id)
            time_dimension.CumulVar(index).SetRange(
                data_model["time_windows"][depot_idx][0],
                data_model["time_windows"][depot_idx][1],
            )

        for i in range(data_model["num_vehicles"]):
            routing.AddVariableMinimizedByFinalizer(time_dimension.CumulVar(routing.Start(i)))
            routing.AddVariableMinimizedByFinalizer(time_dimension.CumulVar(routing.End(i)))

        for node in range(1, len(data_model["time_matrix"])):
            routing.AddDisjunction([manager.NodeToIndex(node)], MAX_PENALTY_TIME)

        search_parameters = pywrapcp.DefaultRoutingSearchParameters()
        search_parameters.first_solution_strategy = (
            routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
        )
        search_parameters.time_limit.FromSeconds(MAX_RUNNING_TIME)

        solution = routing.SolveWithParameters(search_parameters)
        if solution:
            return print_solution(data_model, manager, routing, solution)

        st.warning("No solution found!")
        return []

    result_arr = main_ortools()

    def add_distance_address(result_obj):
        result_obj["Distance"] = [0]
        result_obj["Address/Name"] = []
        result_obj["Address/GPS"] = []

        for index in range(len(result_obj["Routes"]) - 1):
            source = result_obj["Routes"][index]
            dest = result_obj["Routes"][index + 1]
            result_obj["Distance"].append(distance_matrix_arr[source][dest])
            result_obj["Address/Name"].append(id_address[source])
            result_obj["Address/GPS"].append(id_gps[source])

        result_obj["Address/Name"].append(id_address[INDEX_OF_DEPOT])
        result_obj["Address/GPS"].append(id_gps[INDEX_OF_DEPOT])
        result_obj["Total Time (hour)"] = max(result_obj["CumTime"]) / 3600
        result_obj["Total Distance (km)"] = sum(result_obj["Distance"]) / 1000
        result_obj["Total Drop-points (exclude depot)"] = len(result_obj["Routes"]) - 2
        result_obj["Google Maps Route GPS"] = "https://www.google.com/maps/dir/" + "/".join(result_obj["Address/GPS"])
        return result_obj

    result_arr = [
        add_distance_address(result_obj)
        for result_obj in result_arr
        if len(set(result_obj["Routes"])) > 2
    ]

    return pd.DataFrame(result_arr)


def main_app():
    st.title("Henry Duc Lai - Vehicle Routing Problems Demo")

    if not API_KEY:
        st.error("Missing GOOGLE_APIKEY environment variable. Set it before using this page.")
        return

    df_location, config = get_data_location_input()

    if config is not None and df_location is not None:
        with st.spinner("Please wait... Solution is running (<10 minutes)"):
            data_export = calculate_google_map_distance(df_location)
            df_result = calculate_google_or_tools(data_export, config)
            st.balloons()
            st.write(df_result)
            if st.download_button(
                "Download result file",
                file_name="RESULT_ROUTING.csv",
                data=df_result.to_csv(index=False).encode(),
            ):
                st.success("Thanks for downloading...")


if __name__ == "__main__":
    main_app()
