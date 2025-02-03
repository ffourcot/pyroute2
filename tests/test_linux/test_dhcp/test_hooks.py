import json
import logging
import socket
from pyroute2.iproute.linux import AsyncIPRoute
import pytest
from pyroute2.dhcp import hooks
from pyroute2.dhcp.leases import JSONFileLease


FAKE_LEASE = {
  'ack': {
    'op': 2,
    'htype': 1,
    'hlen': 6,
    'hops': 0,
    'xid': 1323206580,
    'secs': 0,
    'flags': 32768,
    'ciaddr': '0.0.0.0',
    'yiaddr': '192.168.186.73',
    'siaddr': '192.168.186.1',
    'giaddr': '0.0.0.0',
    'chaddr': '72:c1:55:6f:76:83',
    'sname': '',
    'file': '',
    'cookie': '63:82:53',
    'options': {
      'message_type': 5,
      'server_id': '192.168.186.1',
      'lease_time': 120,
      'renewal_time': 60,
      'rebinding_time': 105,
      'subnet_mask': '255.255.255.0',
      'broadcast_address': '192.168.186.255',
      'router': [
        '192.168.186.1'
      ],
      'name_server': [
        '192.168.186.1'
      ]
    }
  },
  'interface': '<SET ME>',
  'server_mac': '2e:7e:7d:8e:5f:5f',
  'obtained': 1738249608.073041
}


@pytest.fixture
def fake_lease(dummy_iface: tuple[int, str]) -> JSONFileLease:
    '''Fixture that returns a fake lease loaded from disk.'''
    ifname = dummy_iface[1]
    raw_lease = FAKE_LEASE.copy()
    raw_lease['interface'] = ifname
    JSONFileLease._get_path(ifname).write_text(json.dumps(raw_lease))
    lease = JSONFileLease.load(ifname)
    assert lease
    return lease


async def _ipv4_addrs(ifindex):
    '''Shortcut for `ipr.addr('dump')`.'''
    async with AsyncIPRoute() as ipr:
        return [
            i async for i in await ipr.addr('dump', index=ifindex, family=socket.AF_INET)
        ]


@pytest.mark.asyncio
async def test_add_and_remove_ip_hooks(fake_lease: JSONFileLease, dummy_iface: tuple[int, str], caplog: pytest.LogCaptureFixture):
    '''Test the hooks that add & remove an address from an interface.'''
    caplog.set_level(logging.INFO, logger='pyroute2.dhcp.hooks')

    # call the hook that adds the IP address to the dummy interface
    await hooks.configure_ip(lease=fake_lease)
    ifindex = dummy_iface[0]
    # check the ip addr & broadcast addr have ben set
    assert len(addrs := await _ipv4_addrs(ifindex)) == 1
    addr = addrs[0]
    assert addr.get('IFA_ADDRESS') == fake_lease.ip
    assert addr.get('IFA_BROADCAST') == fake_lease.broadcast_address

    # call the hooks that removes the IP address
    await hooks.remove_ip(lease=fake_lease)
    # check the interface has no address anymore
    assert len(await _ipv4_addrs(ifindex)) == 0

    assert caplog.messages == [
        f'Adding {fake_lease.ip}/{fake_lease.subnet_mask}'
        f' to {fake_lease.interface}',
        f'Removing {fake_lease.ip}/{fake_lease.subnet_mask}'
        f' from {fake_lease.interface}'
    ]