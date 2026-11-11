"""Tests for the STUN hole-punch lifecycle and regression fixes."""

import socket
import time

from punch import PunchRelay

def test_stun_packet_not_learned():
    relay = PunchRelay()
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        relay.set_engine_target("127.0.0.1", 23513)
        relay.start()
        
        import punch
        original_is_loopback = punch._is_loopback
        punch._is_loopback = lambda ip: False  # force all packets to be treated as "from internet"
        try:
            # Send a mocked STUN packet to the relay port
            stun_magic = b"\x01\x01\x00\x00\x21\x12\xA4\x42" + (b"\x00" * 12)
            sock.sendto(stun_magic, ("127.0.0.1", relay.local_port))
            
            time.sleep(0.1)
            # Should NOT have locked the peer
            assert relay.peer is None, f"Peer was incorrectly locked to {relay.peer}"
            assert relay.snapshot["in_from_peer"] == 0
            
            # Send a normal non-STUN packet
            normal_data = b"GAME_DATA_PACKET_NOT_STUN"
            sock.sendto(normal_data, ("127.0.0.1", relay.local_port))
            
            time.sleep(0.1)
            assert relay.peer is not None
            assert relay.snapshot["in_from_peer"] == 1
        finally:
            punch._is_loopback = original_is_loopback
    finally:
        relay.stop()
        sock.close()

def test_host_engine_destination_set():
    relay = PunchRelay()
    relay.set_engine_target("127.0.0.1", 12345)
    assert relay.engine_src == ("127.0.0.1", 12345)
    relay.stop()

def test_delayed_start_prevents_consumption():
    relay = PunchRelay()
    # threads are NOT started.
    assert len(relay._threads) == 0
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.sendto(b"test packet", ("127.0.0.1", relay.local_port))
    time.sleep(0.1)
    
    # We can manually receive from relay.sock because _serve is not running
    relay.sock.settimeout(0.5)
    data, _ = relay.sock.recvfrom(1024)
    assert data == b"test packet"
    
    relay.start()
    assert len(relay._threads) == 2
    relay.stop()
    sock.close()

if __name__ == "__main__":
    test_stun_packet_not_learned()
    test_host_engine_destination_set()
    test_delayed_start_prevents_consumption()
    print("punch lifecycle tests passed")