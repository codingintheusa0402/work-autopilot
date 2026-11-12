import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

TMP = tempfile.mkdtemp(prefix="wa-test-")
os.environ["WA_WORKSPACE"] = TMP
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from autopilot import analyze, config as C, logger, observe, redact, runner, safety, scheduler, sdk  # noqa: E402

AT = "@"


class Redaction(unittest.TestCase):
    def test_redacts_contact_and_ids(self):
        t = redact.redact(f"RE: order from someone{AT}example.com 010-1234-5678 900101-1234567")
        self.assertNotIn(AT, t)
        self.assertIn("[email]", t)
        self.assertIn("[phone]", t)
        self.assertIn("[id]", t)

    def test_card_detection_uses_luhn(self):
        self.assertEqual(redact.looks_sensitive("4111 1111 1111 1111"), "payment card number")
        self.assertIsNone(redact.looks_sensitive("order 1234 5678 9012 3456"))  # fails Luhn

    def test_normalize_groups_repeats(self):
        a = redact.normalize_title("Invoice_2030-03-04 (3).pdf")
        b = redact.normalize_title("Invoice_2030-03-05 (7).pdf")
        self.assertEqual(a, b)


class PrivacyFilter(unittest.TestCase):
    def setUp(self):
        self.cfg = C.load_config()

    def test_password_manager_banking_messaging_dropped(self):
        for app, title, url in [("1Password", "Vault", None), ("KakaoTalk", "chat", None),
                                ("Google Chrome", "Home", "https://www.kbstar.com/x"),
                                ("Google Chrome", "Sign in - password", None)]:
            self.assertIsNone(observe.clean_event(self.cfg, "2030-01-01T09:00:00+09:00", app, title, url, "t"), app)

    def test_work_app_kept_and_url_trimmed(self):
        e = observe.clean_event(self.cfg, "2030-01-01T09:00:00+09:00", "Google Chrome", "Orders",
                                "https://erp.example.com/orders/new?id=55", "t")
        self.assertEqual(e["domain"], "erp.example.com/orders")

    def test_record_command_is_private_by_default(self):
        cmd = observe.record_command(self.cfg)
        for flag in ["--disable-telemetry", "--disable-audio", "--disable-keyboard-capture", "--disable-clipboard-capture"]:
            self.assertIn(flag, cmd)
        self.assertNotIn("deepgram", " ".join(cmd).lower())
        self.assertIn(str(observe.SP_DATA), cmd)         # our own data dir, never ~/.screenpipe


class Analysis(unittest.TestCase):
    def test_sample_week(self):
        cfg = C.load_config()
        raw = observe.load_events([C.ROOT / "samples" / "synthetic_week" / "events.jsonl.gz"])
        kept = [e for e in (observe.clean_event(cfg, x["ts"], x["app"], x["title"], x.get("domain"), x["src"]) for x in raw) if e]
        self.assertLess(len(kept), len(raw))                 # the fake KakaoTalk/1Password rows are gone
        r = analyze.analyze(kept)
        self.assertTrue(r["synthetic"])
        self.assertEqual(r["days_observed"], 5)
        self.assertGreaterEqual(len(r["tasks"]), 8)
        verdicts = {t["verdict"] for t in r["tasks"]}
        self.assertEqual(verdicts, {"automatable", "ai_assistable", "keep_human"})
        meeting = next(t for t in r["tasks"] if t["category"] == "meeting")
        self.assertEqual(meeting["verdict"], "keep_human")
        self.assertTrue(any(len(w["steps"]) >= 3 and w["days_seen"] == 5 for w in r["workflows"]))
        self.assertFalse(any(t["app"] in ("KakaoTalk", "1Password") for t in r["tasks"]))


def install_demo():
    C.ensure_workspace()
    dst = C.AUTO_DIR / "demo-invoice-sorter"
    shutil.rmtree(dst, ignore_errors=True)
    shutil.copytree(C.ROOT / "examples" / "automations" / "demo-invoice-sorter", dst)
    shutil.copy(C.ROOT / "examples" / "specs" / "demo-invoice-sorter.md", C.SPEC_DIR / "demo-invoice-sorter.md")
    inbox = C.WORKSPACE / "demo_files" / "Downloads"
    shutil.rmtree(inbox.parent, ignore_errors=True)
    inbox.mkdir(parents=True)
    for n in ("Invoice_1_Alpha.pdf", "Invoice_2_Beta.pdf", "notes.txt"):
        (inbox / n).write_text("fake")
    return dst, inbox


def quiet(fn, *a, **k):
    with mock.patch("sys.stdout", new=io.StringIO()):
        return fn(*a, **k)


class Automations(unittest.TestCase):
    def test_dry_run_changes_nothing_then_live_and_undo(self):
        dst, inbox = install_demo()
        self.assertEqual(quiet(runner.run, "demo-invoice-sorter", live=True), 2)   # not tested yet
        self.assertEqual(quiet(runner.test, "demo-invoice-sorter"), 0)
        self.assertEqual(len(list(inbox.iterdir())), 3)                          # dry-run moved nothing
        self.assertEqual(quiet(runner.run, "demo-invoice-sorter", live=True), 0)
        self.assertEqual([p.name for p in inbox.iterdir()], ["notes.txt"])
        last = runner.recent_runs(1)[-1]
        self.assertEqual(last["mode"], "live")
        self.assertEqual(len(last["blocked"]), 1)                                # send_message not approved
        quiet(sdk.undo, last["run_id"])
        self.assertEqual(len(list(inbox.iterdir())), 3)
        self.assertEqual(runner.recent_runs(1)[-1]["minutes_saved"], 0)          # undone runs save nothing

    def test_code_change_invalidates_test(self):
        dst, _ = install_demo()
        quiet(runner.test, "demo-invoice-sorter")
        with open(dst / "run.py", "a") as f:
            f.write("\n# changed\n")
        self.assertEqual(quiet(runner.run, "demo-invoice-sorter", live=True), 2)

    def test_agent_cannot_approve(self):
        dst, _ = install_demo()
        with mock.patch("sys.stdin", new=io.StringIO("demo-invoice-sorter\n")):
            self.assertEqual(quiet(safety.approve, "demo-invoice-sorter", "send_message", dst, "x"), 3)

    def test_lint_catches_secrets_and_undeclared_sends(self):
        dst, _ = install_demo()
        (dst / "bad.py").write_text('password = "hunter2"\nimport smtplib\n')
        errors, _ = safety.lint(dst)
        self.assertTrue(any("민감" in e for e in errors))
        self.assertFalse(any("send_message" in e for e in errors))   # declared in this manifest → warning only
        m = json.loads((dst / "automation.json").read_text())
        m["risky_actions"] = {}
        (dst / "automation.json").write_text(json.dumps(m))
        errors, _ = safety.lint(dst)
        self.assertTrue(any("send_message" in e for e in errors))

    def test_spec_gate(self):
        dst, _ = install_demo()
        (C.SPEC_DIR / "demo-invoice-sorter.md").write_text("TODO(ask): what is done?\n")
        self.assertEqual(quiet(runner.test, "demo-invoice-sorter"), 2)


class Scheduling(unittest.TestCase):
    def test_plans_for_each_os(self):
        install_demo()
        quiet(runner.test, "demo-invoice-sorter")
        with mock.patch("platform.system", return_value="Darwin"):
            p = scheduler.plan("demo-invoice-sorter", live=True)
            self.assertEqual(p["system"], "launchd")
            self.assertEqual(len(p["plist"]["StartCalendarInterval"]), 5)
            self.assertIn("--live", p["plist"]["ProgramArguments"])
        with mock.patch("platform.system", return_value="Linux"):
            p = scheduler.plan("demo-invoice-sorter", live=False)
            self.assertTrue(p["line"].startswith("30 13 * * 1,2,3,4,5 "))
            self.assertNotIn("--live", p["line"])
        with mock.patch("platform.system", return_value="Windows"):
            p = scheduler.plan("demo-invoice-sorter", live=True)
            self.assertIn("MON,TUE,WED,THU,FRI", p["create"])

    def test_launchd_install_to_temp_dir(self):
        install_demo()
        quiet(runner.test, "demo-invoice-sorter")
        agents = Path(TMP) / "LaunchAgents"
        with mock.patch.dict(os.environ, {"WA_LAUNCHAGENTS_DIR": str(agents), "WA_SCHEDULER_NOLOAD": "1"}), \
                mock.patch("platform.system", return_value="Darwin"):
            self.assertEqual(quiet(scheduler.schedule, "demo-invoice-sorter", True, True), 0)
            self.assertEqual(len(list(agents.glob("*.plist"))), 1)
            quiet(scheduler.unschedule, "demo-invoice-sorter")
            self.assertEqual(len(list(agents.glob("*.plist"))), 0)


class ExportParsing(unittest.TestCase):
    def test_export_keeps_metadata_only(self):
        """Fake screenpipe /search pages (shape from screenpipe's routes/content.rs)."""
        cfg = C.load_config()
        pages = {
            "ocr": [{"type": "OCR", "content": {"timestamp": "2030-01-01T00:00:00Z", "app_name": "Excel",
                                                "window_name": "orders.xlsx", "browser_url": None, "text": "SECRET SCREEN TEXT"}},
                    {"type": "OCR", "content": {"timestamp": "2030-01-01T00:00:05Z", "app_name": "1Password",
                                                "window_name": "Vault", "text": "x"}}],
            "accessibility": [{"type": "UI", "content": {"timestamp": "2030-01-01T00:00:10Z", "app_name": "Google Chrome",
                                                          "window_name": "Orders", "browser_url": "https://erp.example.com/o?id=1", "text": "y"}},
                              {"type": "Audio", "content": {"timestamp": "2030-01-01T00:00:11Z"}}],
        }

        def fake_get(url):
            from urllib.parse import parse_qs, urlparse
            q = parse_qs(urlparse(url).query)
            return {"data": pages[q["content_type"][0]] if q["offset"][0] == "0" else []}

        with mock.patch.object(observe, "health", return_value={"status": "healthy"}), \
                mock.patch.object(observe, "_get", side_effect=fake_get):
            out = quiet(observe.export, cfg, "2030-01-01T00:00:00Z", "2030-01-02T00:00:00Z")
        rows = observe.load_events([out])
        self.assertEqual([r["app"] for r in rows], ["Excel", "Google Chrome"])
        self.assertEqual(rows[1]["domain"], "erp.example.com/o")
        self.assertNotIn("SECRET", json.dumps(rows))


class BuiltinLogger(unittest.TestCase):
    def test_logs_metadata_respects_excludes_and_include_list(self):
        import datetime as dt
        cfg = C.load_config()
        cfg.update(logger_interval_s=0, logger_screenshot_every_s=1, include_windows=["WA-FAKE", "1Password"])
        seq = iter([{"app": "TextEdit", "title": "WA-FAKE-orders.txt", "wid": 7},
                    {"app": "1Password", "title": "WA-FAKE vault", "wid": 8},       # excluded even if included
                    {"app": "Mail", "title": "Inbox", "wid": 9}])                    # not on the include list
        shots = []
        for f in C.OBS_DIR.glob("builtin-*.jsonl"):
            f.unlink()
        with mock.patch.object(logger, "front_window", side_effect=lambda: next(seq)), \
                mock.patch.object(logger, "idle_seconds", return_value=0), \
                mock.patch.object(logger, "screenshot", side_effect=lambda w, p: shots.append(w["app"]) or True):
            quiet(logger.loop, cfg, dt.datetime.now().astimezone() + dt.timedelta(minutes=1), max_ticks=3)
        rows = observe.load_events(sorted(C.OBS_DIR.glob("builtin-*.jsonl")))
        self.assertEqual([(r["app"], r["src"]) for r in rows], [("TextEdit", "builtin")])
        self.assertEqual(shots, ["TextEdit"])

    def test_screenpipe_gets_include_list(self):
        cfg = C.load_config()
        cfg["include_windows"] = ["WA-FAKE"]
        cmd = observe.record_command(cfg)
        self.assertIn("--included-windows", cmd)
        self.assertEqual(cmd[cmd.index("--included-windows") + 1], "WA-FAKE")


class ApprovedPath(unittest.TestCase):
    def test_approved_risky_action_runs_in_live_mode_only(self):
        dst, _ = install_demo()
        calls = []
        env = {"WA_AUTOMATION_DIR": str(dst), "WA_MODE": "live", "WA_RUN_ID": "t-approved"}
        with mock.patch.dict(os.environ, env), mock.patch.object(sdk, "is_approved", return_value=True):
            with quiet(sdk.Run) as run:
                run.risky("send_message", "x", lambda: calls.append(1))
        self.assertEqual(calls, [1])
        with mock.patch.dict(os.environ, dict(env, WA_MODE="dry", WA_RUN_ID="t-dry")), \
                mock.patch.object(sdk, "is_approved", return_value=True):
            with quiet(sdk.Run) as run:
                run.risky("send_message", "x", lambda: calls.append(2))
        self.assertEqual(calls, [1])          # dry-run never performs it, approved or not


def tearDownModule():
    shutil.rmtree(TMP, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
