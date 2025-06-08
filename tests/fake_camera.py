"""Replay captured network traffic to simulate the noname wireless camera."""
import argparse
import time
from scapy.all import rdpcap, IP, UDP, sendp


def replay_pcap(pcap_path: str, iface: str, ip_map=None, port_map=None) -> None:
    """Replay packets from a PCAP file with optional IP/port rewriting."""
    packets = rdpcap(pcap_path)
    if not packets:
        return
    start_time = packets[0].time
    send_start = time.time()
    ip_map = ip_map or {}
    port_map = port_map or {}
    for pkt in packets:
        if IP in pkt:
            if pkt[IP].src in ip_map:
                pkt[IP].src = ip_map[pkt[IP].src]
            if pkt[IP].dst in ip_map:
                pkt[IP].dst = ip_map[pkt[IP].dst]
            del pkt[IP].len
            del pkt[IP].chksum
        if UDP in pkt:
            if pkt[UDP].sport in port_map:
                pkt[UDP].sport = port_map[pkt[UDP].sport]
            if pkt[UDP].dport in port_map:
                pkt[UDP].dport = port_map[pkt[UDP].dport]
            del pkt[UDP].len
            del pkt[UDP].chksum
        delay = pkt.time - start_time - (time.time() - send_start)
        if delay > 0:
            time.sleep(delay)
        sendp(pkt, iface=iface, verbose=False)


def main() -> None:
    parser = argparse.ArgumentParser(description="Replay captured camera traffic")
    parser.add_argument("pcap", help="Path to PCAP file")
    parser.add_argument("--iface", default="eth0", help="Interface to send packets on")
    parser.add_argument("--client-ip", help="Override client IP address")
    parser.add_argument("--camera-ip", help="Override camera IP address")
    parser.add_argument("--client-port", type=int, help="Override client video port")
    args = parser.parse_args()

    ip_map = {}
    if args.client_ip:
        ip_map["10.215.173.1"] = args.client_ip
    if args.camera_ip:
        ip_map["192.168.4.153"] = args.camera_ip

    port_map = {}
    if args.client_port:
        port_map[42243] = args.client_port

    replay_pcap(args.pcap, args.iface, ip_map, port_map)


if __name__ == "__main__":
    main()
