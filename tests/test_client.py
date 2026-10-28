"""Parser tests for the router client: python3 -m unittest discover tests"""

import importlib.util
from pathlib import Path
import sys
import unittest

CLIENT = Path(__file__).resolve().parent.parent / "custom_components" / "zte_presence" / "client.py"
spec = importlib.util.spec_from_file_location("zte_client", CLIENT)
zte = importlib.util.module_from_spec(spec)
sys.modules["zte_client"] = zte
spec.loader.exec_module(zte)

XML = """<ajax_response_xml_root><IF_ERRORSTR>SUCC</IF_ERRORSTR>
<OBJ_WLAN_AD_ID><Instance>
<ParaName>_InstID</ParaName><ParaValue>DEV.WIFI.AP1.AD1</ParaValue>
<ParaName>MACAddress</ParaName><ParaValue>02:00:00:00:00:01</ParaValue>
<ParaName>IPAddress</ParaName><ParaValue>192.168.0.57</ParaValue>
<ParaName>HostName</ParaName><ParaValue>phone</ParaValue>
</Instance></OBJ_WLAN_AD_ID>
<OBJ_WLANAP_ID><Instance><ParaName>ESSID</ParaName><ParaValue>home</ParaValue></Instance></OBJ_WLANAP_ID>
</ajax_response_xml_root>"""

JSON = """{"OBJ_WLAN_AD_ID": {"Instance": [{"path": "DEV.WIFI.AP1.AD1",
"parameters": {"MACAddress": "02:00:00:00:00:01", "IPAddress": "192.168.0.57", "HostName": "phone"}}]},
"OBJ_WLANAP_ID": {"Instance": {"path": "AP1", "parameters": {"ESSID": "home"}}}}"""


# H3601P mesh unit: accessdev_ssiddev_lua.lua
MESH = """<ajax_response_xml_root><IF_ERRORSTR>SUCC</IF_ERRORSTR>
<OBJ_ACCESSDEV_ID><Instance>
<ParaName>_InstID</ParaName><ParaValue>DEV.HOST1</ParaValue>
<ParaName>AliasName</ParaName><ParaValue>SSID1</ParaValue>
<ParaName>HostName</ParaName><ParaValue>iPhone</ParaValue>
<ParaName>IPAddress</ParaName><ParaValue>192.168.0.57</ParaValue>
<ParaName>MACAddress</ParaName><ParaValue>02:00:00:00:00:01</ParaValue>
</Instance></OBJ_ACCESSDEV_ID>
</ajax_response_xml_root>"""


class ParseTest(unittest.TestCase):
    def test_mesh(self):
        self.assertEqual(
            zte.parse_clients(MESH, "192.168.0.22"),
            [zte.NetworkClient("02:00:00:00:00:01", "192.168.0.57", "iPhone", "192.168.0.22")],
        )

    def test_xml(self):
        self.assertEqual(
            zte.parse_clients(XML, "192.168.0.13"),
            [zte.NetworkClient("02:00:00:00:00:01", "192.168.0.57", "phone", "192.168.0.13")],
        )

    def test_json(self):
        self.assertEqual(
            zte.parse_clients(JSON, "192.168.0.13"),
            [zte.NetworkClient("02:00:00:00:00:01", "192.168.0.57", "phone", "192.168.0.13")],
        )

    def test_session_timeout_is_error(self):
        with self.assertRaises(zte.ZteError):
            zte.parse_clients(
                "<ajax_response_xml_root><IF_ERRORSTR>SessionTimeout</IF_ERRORSTR></ajax_response_xml_root>", "192.168.0.13"
            )


class LockingTimeTest(unittest.TestCase):
    def test_number_or_string(self):
        self.assertEqual(zte._locking_time({"lockingTime": 60}), 60)
        self.assertEqual(zte._locking_time({"lockingTime": "60"}), 60)
        self.assertEqual(zte._locking_time({"lockingTime": "0"}), 0)
        self.assertEqual(zte._locking_time({}), 0)
        self.assertEqual(zte._locking_time({"lockingTime": "soon"}), 0)


if __name__ == "__main__":
    unittest.main()
