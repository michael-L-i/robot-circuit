import pytest
from scripts.instruments.read_dm40 import decode


def test_observed_packets_and_sign():
    assert decode(bytes.fromhex('df0503090b3002000019ffffffff0c00b2'))['volts'] == -.0012
    assert decode(bytes.fromhex('df0503090b3002000018ffffffff560069'))['volts'] == .0086


def test_bad_checksum_rejected():
    with pytest.raises(ValueError):
        decode(bytes.fromhex('df0503090b3002000018ffffffff560068'))


def test_other_modes_and_overload_never_report_zero_volts():
    p=bytearray.fromhex('df0503090b3002000018ffffffff560069')
    p[5]=2;p[-1]=(-sum(p[:-1]))%256
    assert decode(p)['volts'] is None
    p[5]=0x30;p[14:16]=b'\xff\xff';p[-1]=(-sum(p[:-1]))%256
    assert decode(p)['status']=='overload'
    assert decode(p)['volts'] is None
