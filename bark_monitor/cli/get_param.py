import argparse
import json


def get_parameters() -> tuple[bool, str, str, str, str | None, int, int, str | None, str | None, str | None, bool]:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config-file",
        type=str,
        help="Path to config file",
        default="config.json",
    )
    parser.add_argument(
        "--accept-new-users",
        action=argparse.BooleanOptionalAction,
        help="If true new users will be accepted by the bot",
    )

    args = parser.parse_args()
    with open(args.config_file, "rb") as f:
        json_data = json.load(f)

    things_board_url = None
    if (
        "thingsboard_ip" in json_data
        and "thingsboard_port" in json_data
        and "thingsboard_device_token" in json_data
    ):
        things_board_url = (
            "http://"
            + json_data["thingsboard_ip"]
            + ":"
            + str(json_data["thingsboard_port"])
            + "/api/v1/"
            + json_data["thingsboard_device_token"]
            + "/telemetry"
        )

    microphone_framerate = (
        json_data["microphone framerate"]
        if "microphone framerate" in json_data
        else 16000
    )

    sampling_time_bark_seconds = (
        json_data["sampling time bark seconds"]
        if "sampling time bark seconds" in json_data
        else 1
    )
    try:
        debug_print = int(json_data["debug_print"]) > 0
    except:
        debug_print = False

    return (
        args.accept_new_users,
        json_data["api_key"],
        json_data["output_folder"],
        json_data["config_folder"],
        things_board_url,
        microphone_framerate,
        sampling_time_bark_seconds,
        json_data.get("google credentials"),
        json_data.get("audio_device"),
        json_data.get("output_data_file"),
        debug_print
    )
