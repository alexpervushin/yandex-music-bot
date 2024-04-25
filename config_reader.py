import toml


def read_config(file_path):
    with open(file_path, "r") as file:
        config = toml.load(file)
    return config


config = read_config("config.toml")

token = config["telegram"]["token"]
mongodb_server = config["mongodb"]["server"]
mongodb_port = config["mongodb"]["port"]
server_enabled = config["server"]["enabled"]
host = config["server"]["host"]
port = config["server"]["port"]
address = config["server"].get("address", None)
