import tempfile
import unittest
from pathlib import Path

from orchestra.ssh_config import local_ssh_hosts


class OpenSSHConfigTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.home = Path(temporary.name)
        self.ssh = self.home / ".ssh"
        self.ssh.mkdir()

    def write(self, name, body):
        path = self.ssh / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")

    def hosts(self):
        return local_ssh_hosts(self.home, local_user="local-user")

    def test_include_order_patterns_and_connection_fields(self):
        self.write("config", '''
            Include ~/.ssh/config.d/*.conf
            Host DEV
                HostName ignored.example.test
                Port 2222
            Host * !plain
                User default-user
                Port 2200
            Host ipv6
                HostName=2001:db8::1
            Host plain
        ''')
        self.write("config.d/20-late.conf", "Host dev\n HostName later.example.test\n")
        self.write("config.d/10-early.conf", '''
            Host dev backup *.lab !ignore
                HostName=%h.example.test # suffix
                User "DOMAIN\\fixture"
                IdentityFile "~/.ssh/deploy keys/%n #1"
            Host optional
                IdentityFile "%d/.ssh/%r-%p"
        ''')
        hosts = self.hosts()
        self.assertEqual(list(hosts), ["dev", "backup", "optional", "ipv6", "plain"])
        self.assertEqual(hosts["dev"], {"host": "dev.example.test", "user": "DOMAIN\\fixture", "port": "2222",
                                        "identity": str(self.ssh / "deploy keys" / "dev #1"), "proxy": False})
        self.assertEqual(hosts["backup"]["port"], "2200")
        self.assertEqual(hosts["optional"]["identity"], str(self.ssh / "default-user-2200"))
        self.assertEqual(hosts["ipv6"]["host"], "2001:db8::1")
        self.assertEqual(hosts["plain"]["user"], "local-user")
        self.assertEqual(hosts["plain"]["port"], "22")

    def test_only_config_inside_ssh_and_never_evaluate_match(self):
        (self.home / "outside").write_text("Host outside\n", encoding="utf-8")
        self.write("config", '''
            Include ../outside
            Host internal
                Include nested
                Port 2022
            Host match-block
            Match exec "must-not-run"
                HostName ignored.example.test
                Include match-only
            Host direct
                ProxyCommand none
                ProxyJump ignored
        ''')
        self.write("nested", "Include config\nProxyCommand ssh gateway -W %h:%p\nHost unrelated\n")
        self.write("match-only", "Host never-visible\n")
        hosts = self.hosts()
        self.assertEqual(list(hosts), ["internal", "match-block", "direct"])
        self.assertEqual(hosts["internal"]["port"], "2022")
        self.assertTrue(hosts["internal"]["proxy"])
        self.assertEqual(hosts["match-block"]["host"], "match-block")
        self.assertFalse(hosts["direct"]["proxy"])

    def test_missing_and_malformed_entries(self):
        self.assertEqual(self.hosts(), {})
        self.write("config", 'Host broken "\n HostName ignored\nHost okay\n HostName valid.example.test\n')
        self.assertEqual(list(self.hosts()), ["okay"])
