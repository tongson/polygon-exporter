from urllib.parse import urlparse
import time
import argparse
import sys
import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry
import prometheus_client
from prometheus_client import REGISTRY


def new_https() -> requests.Session:
    retry_strategy = Retry(
        total=4,
        status_forcelist=[104, 408, 425, 429, 500, 502, 503, 504],
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session = requests.Session()
    session.mount("https://", adapter)
    return session


def read_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Polygon Exporter.")
    parser.add_argument(
        "--port",
        metavar="PORT",
        type=int,
        default=9099,
        help="The port used to export the metrics. Default is 9099.",
    )
    parser.add_argument(
        "--bor",
        metavar="BOR",
        default=False,
        type=str,
        help="Bor RPC endpoint.",
    )
    parser.add_argument(
        "--heimdall",
        metavar="HEIMDALL",
        default=False,
        type=str,
        help="Heimdall REST endpoint.",
    )
    parser.add_argument(
        "--staking",
        metavar="STAKING",
        default=False,
        type=str,
        help="Polygon Staking REST endpoint.",
    )
    parser.add_argument(
        "--validator",
        metavar="VALIDATOR",
        default=False,
        type=str,
        help="Validator ID.",
    )
    parser.add_argument(
        "--freq",
        metavar="SEC",
        type=int,
        default=300,
        help="Update frequency in seconds. Default is 300 seconds (5 minutes).",
    )
    return parser.parse_args()


def get_bor_height(endpoint: str) -> float:
    session = new_https()
    try:
        resp = session.post(
            endpoint,
            json={
                "jsonrpc": "2.0",
                "method": "eth_getBlockByNumber",
                "params": ["latest", True],
                "id": 1,
            },
        )
    except Exception as e:
        return float(0)
    else:
        if resp.status_code == 200:
            data = resp.json()
            blockhex = data["result"]["number"]
            block = int(blockhex, 16)
            return float(block)
        else:
            return float(0)


def get_heimdall_height(endpoint: str) -> tuple[float, float]:
    session = new_https()
    try:
        resp = session.get(f"{endpoint}/checkpoints/latest")
    except Exception as e:
        return float(0), float(0)
    else:
        if resp.status_code == 200:
            data = resp.json()
            ht = data["height"]
            cp = data["result"]["id"]
            return float(data["height"]), float(data["result"]["id"])
        else:
            return float(0), float(0)


def get_local_height(endpoint: str, validator: str) -> float:
    session = new_https()
    try:
        resp = session.get(
            f"{endpoint}/api/v2/validators/{validator}/checkpoints-signed?limit=1&offset=0"
        )
    except Exception as e:
        return float(0)
    else:
        if resp.status_code == 200:
            data = resp.json()
            return float(data["result"][0]["checkpointNumber"])
        else:
            return float(0)


if __name__ == "__main__":
    args = read_args()
    for coll in list(REGISTRY._collector_to_names.keys()):
        REGISTRY.unregister(coll)
    try:
        prometheus_client.start_http_server(args.port)
    except Exception as e:
        e.add_note("\nError starting HTTP server.")
        raise
    else:
        bor = prometheus_client.Gauge(
            "polygon_latest_bor_height",
            "Polygon Latest Bor Height",
            ["external_endpoint"],
        )
        heimdall = prometheus_client.Gauge(
            "polygon_latest_heimdall_height",
            "Polygon Latest Heimdall Height",
            ["external_endpoint"],
        )
        checkpoint = prometheus_client.Gauge(
            "polygon_latest_checkpoint_height",
            "Polygon Latest Checkpoint Height",
            ["external_endpoint"],
        )
        local = prometheus_client.Gauge(
            "polygon_local_checkpoint_height",
            "Polygon Local Checkpoint Height",
            ["external_endpoint"],
        )
        while True:
            bor_height = get_bor_height(args.bor)
            heimdall_height, checkpoint_height = get_heimdall_height(args.heimdall)
            local_height = get_local_height(args.staking, args.validator)
            sys.stdout.write(f"Bor: {str(bor_height)}\n")
            sys.stdout.write(f"Heimdall: {str(heimdall_height)}\n")
            sys.stdout.write(f"Checkpoint: {str(checkpoint_height)}\n")
            sys.stdout.write(f"Local: {str(local_height)}\n")
            if bor_height > 1:
                bor.labels(urlparse(args.bor).hostname).set(bor_height)
            if heimdall_height > 1:
                heimdall.labels(urlparse(args.heimdall).hostname).set(heimdall_height)
            if checkpoint_height > 1:
                checkpoint.labels(urlparse(args.heimdall).hostname).set(
                    checkpoint_height
                )
            if local_height > 1:
                local.labels(urlparse(args.staking).hostname).set(local_height)
            time.sleep(args.freq)
