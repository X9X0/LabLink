"""Alarm and scheduler API tests, against the API rather than around it.

Every test in this file used to pass without touching the endpoints it names.
The alarm and scheduler routers were commented out of the test app, so each
request returned 404 -- and each assertion accepted 404:

    assert response.status_code in [200, 404]

Which holds whether the API works perfectly or does not exist. Twenty-six
tests reported green over sixteen alarm routes and twelve scheduler routes
that had never been exercised, and three more skipped with "Alarms API not
implemented" while `server/api/alarms.py` sat there implementing it. The
requests were also aimed at `/api/alarms`, which is not a route; the real one
is `/api/alarms/create`.

These now run against the real managers via the `alarms_client` fixture: the
alarm manager is in-memory, and the scheduler gets a temporary SQLite file. No
assertion accepts a 404 unless absence is the thing being tested.
"""

import pytest


def alarm_payload(**overrides):
    """A valid CreateAlarmRequest body.

    `enabled` defaults to False: creating an enabled threshold alarm starts a
    monitoring task against equipment that does not exist here, and the point
    of most of these tests is the API, not the monitor.
    """
    payload = {
        "name": "Overvoltage",
        "description": "Supply above its limit",
        "equipment_id": "ps_001",
        "parameter": "voltage",
        "alarm_type": "threshold",
        "condition": "greater_than",
        "severity": "warning",
        "threshold": 12.5,
        "enabled": False,
        "tags": ["bench"],
    }
    payload.update(overrides)
    return payload


def job_payload(**overrides):
    """A valid CreateJobRequest body."""
    payload = {
        "name": "Nightly measurement",
        "description": "Take a reading at 9am",
        "schedule_type": "measurement",
        "equipment_id": "ps_001",
        "trigger_type": "cron",
        "cron_expression": "0 9 * * *",
        "enabled": False,
        "tags": ["bench"],
    }
    payload.update(overrides)
    return payload


def create_alarm(client, **overrides) -> str:
    response = client.post("/api/alarms/create", json=alarm_payload(**overrides))
    assert response.status_code == 200, response.text
    return response.json()["alarm_id"]


def create_job(client, **overrides) -> str:
    response = client.post("/api/scheduler/jobs/create", json=job_payload(**overrides))
    assert response.status_code == 200, response.text
    return response.json()["job_id"]


class TestAlarmManagement:
    """Alarm CRUD."""

    def test_create_alarm_success(self, alarms_client):
        response = alarms_client.post("/api/alarms/create", json=alarm_payload())

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["success"] is True
        assert body["alarm_id"]

    def test_a_created_alarm_is_retrievable(self, alarms_client):
        """The old version asserted a status code and never read anything back."""
        alarm_id = create_alarm(alarms_client, name="Undervoltage", threshold=4.5)

        alarm = alarms_client.get(f"/api/alarms/{alarm_id}").json()["alarm"]

        assert alarm["name"] == "Undervoltage"
        assert alarm["threshold"] == 4.5
        assert alarm["parameter"] == "voltage"

    def test_create_alarm_rejects_a_missing_required_field(self, alarms_client):
        response = alarms_client.post("/api/alarms/create", json={"name": "no parameter"})

        assert response.status_code == 422

    def test_create_alarm_rejects_an_unknown_severity(self, alarms_client):
        """AlarmConfig validates the enum; the route turns that into a 400."""
        response = alarms_client.post(
            "/api/alarms/create", json=alarm_payload(severity="catastrophic")
        )

        assert response.status_code == 400
        assert "severity" in response.text

    def test_get_unknown_alarm_is_404(self, alarms_client):
        """A 404 asserted deliberately, rather than tolerated everywhere."""
        assert alarms_client.get("/api/alarms/no-such-alarm").status_code == 404

    def test_list_alarms(self, alarms_client):
        first = create_alarm(alarms_client, name="First")
        second = create_alarm(alarms_client, name="Second")

        body = alarms_client.get("/api/alarms").json()

        listed = {a["alarm_id"] for a in body["alarms"]}
        assert {first, second} <= listed
        assert body["count"] >= 2

    def test_update_alarm(self, alarms_client):
        alarm_id = create_alarm(alarms_client, threshold=12.5)

        response = alarms_client.put(
            f"/api/alarms/{alarm_id}", json={"threshold": 15.0, "severity": "critical"}
        )

        assert response.status_code == 200, response.text
        after = alarms_client.get(f"/api/alarms/{alarm_id}").json()["alarm"]
        assert after["threshold"] == 15.0
        assert after["severity"] == "critical"

    def test_delete_alarm(self, alarms_client):
        alarm_id = create_alarm(alarms_client)

        assert alarms_client.delete(f"/api/alarms/{alarm_id}").status_code == 200
        assert alarms_client.get(f"/api/alarms/{alarm_id}").status_code == 404

    def test_enable_and_disable(self, alarms_client):
        alarm_id = create_alarm(alarms_client, enabled=False)

        assert alarms_client.post(f"/api/alarms/{alarm_id}/enable").status_code == 200
        assert alarms_client.get(f"/api/alarms/{alarm_id}").json()["alarm"]["enabled"] is True

        assert alarms_client.post(f"/api/alarms/{alarm_id}/disable").status_code == 200
        assert alarms_client.get(f"/api/alarms/{alarm_id}").json()["alarm"]["enabled"] is False


class TestAlarmEvents:
    """Triggering, acknowledgement and history."""

    def test_active_events_starts_empty(self, alarms_client):
        body = alarms_client.get("/api/alarms/events/active").json()

        assert body["events"] == []

    def test_event_history_is_a_list(self, alarms_client):
        create_alarm(alarms_client)

        body = alarms_client.get("/api/alarms/events").json()

        assert isinstance(body["events"], list)

    def test_acknowledging_an_unknown_event_is_rejected(self, alarms_client):
        """The old test acknowledged nothing and accepted 404 as success."""
        response = alarms_client.post(
            "/api/alarms/events/acknowledge",
            json={"event_id": "no-such-event", "acknowledged_by": "operator"},
        )

        assert response.status_code in (400, 404)

    def test_check_runs_against_a_created_alarm(self, alarms_client):
        alarm_id = create_alarm(alarms_client)

        response = alarms_client.post(
            "/api/alarms/check",
            json={"alarm_id": alarm_id, "equipment_id": "ps_001",
                  "parameter": "voltage", "value": 13.0},
        )

        assert response.status_code == 200, response.text
        assert alarms_client.get(f"/api/alarms/{alarm_id}").status_code == 200

    def test_statistics_are_reported(self, alarms_client):
        create_alarm(alarms_client)

        response = alarms_client.get("/api/alarms/statistics")

        # Explicitly 200: a 404 body is also "a non-empty dict", which is how
        # this file used to pass while testing nothing.
        assert response.status_code == 200, response.text
        assert response.json()["success"] is True
        assert "statistics" in response.json()


class TestAlarmNotifications:
    """Notification configuration."""

    def test_configure_notifications(self, alarms_client):
        response = alarms_client.post(
            "/api/alarms/notifications/configure",
            json={"channel": "email", "enabled": True,
                  "config": {"recipients": ["bench@example.com"]}},
        )

        assert response.status_code == 200, response.text

    def test_configuration_is_readable(self, alarms_client):
        response = alarms_client.get("/api/alarms/notifications/config")

        assert response.status_code == 200
        assert isinstance(response.json(), dict)


class TestSchedulerJobManagement:
    """Job CRUD."""

    def test_create_job_success(self, alarms_client):
        response = alarms_client.post("/api/scheduler/jobs/create", json=job_payload())

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["success"] is True
        assert body["job_id"]

    def test_a_created_job_is_retrievable(self, alarms_client):
        job_id = create_job(alarms_client, name="Hourly capture")

        job = alarms_client.get(f"/api/scheduler/jobs/{job_id}").json()["job"]

        assert job["name"] == "Hourly capture"
        assert job["trigger_type"] == "cron"

    def test_create_job_rejects_missing_required_fields(self, alarms_client):
        response = alarms_client.post("/api/scheduler/jobs/create", json={"name": "nothing else"})

        assert response.status_code == 422

    @pytest.mark.xfail(
        strict=True,
        reason="The scheduler accepts an invalid cron expression: "
               "validate_cron_expression is unimplemented, which is also why "
               "two tests in tests/server/scheduler skip. When it is "
               "implemented this will XPASS -- turn it into a plain assert.",
    )
    def test_create_job_rejects_an_invalid_cron_expression(self, alarms_client):
        response = alarms_client.post(
            "/api/scheduler/jobs/create",
            json=job_payload(cron_expression="not a cron", enabled=True),
        )

        assert response.status_code >= 400

    def test_get_unknown_job_is_404(self, alarms_client):
        assert alarms_client.get("/api/scheduler/jobs/no-such-job").status_code == 404

    def test_list_jobs(self, alarms_client):
        first = create_job(alarms_client, name="First")
        second = create_job(alarms_client, name="Second")

        body = alarms_client.get("/api/scheduler/jobs").json()

        listed = {j["job_id"] for j in body["jobs"]}
        assert {first, second} <= listed

    def test_delete_job(self, alarms_client):
        job_id = create_job(alarms_client)

        assert alarms_client.delete(f"/api/scheduler/jobs/{job_id}").status_code == 200
        assert alarms_client.get(f"/api/scheduler/jobs/{job_id}").status_code == 404


class TestSchedulerJobControl:
    """Pause, resume and manual run."""

    def test_pause_and_resume(self, alarms_client):
        job_id = create_job(alarms_client, enabled=True)

        assert alarms_client.post(f"/api/scheduler/jobs/{job_id}/pause").status_code == 200
        assert alarms_client.post(f"/api/scheduler/jobs/{job_id}/resume").status_code == 200

    def test_pause_unknown_job_is_rejected(self, alarms_client):
        response = alarms_client.post("/api/scheduler/jobs/no-such-job/pause")

        assert response.status_code in (400, 404)

    def test_trigger_job_manually(self, alarms_client):
        job_id = create_job(alarms_client)

        response = alarms_client.post(f"/api/scheduler/jobs/{job_id}/run")

        assert response.status_code == 200, response.text


class TestSchedulerHistory:
    """Executions and statistics."""

    def test_job_history_summarises_the_job(self, alarms_client):
        """`history` is a summary object, not the list of executions.

        The executions themselves are at /scheduler/executions; this endpoint
        returns counters for one job.
        """
        job_id = create_job(alarms_client)

        response = alarms_client.get(f"/api/scheduler/jobs/{job_id}/history")

        assert response.status_code == 200, response.text
        history = response.json()["history"]
        assert history["job_id"] == job_id
        assert history["failed"] == 0

    def test_recent_executions(self, alarms_client):
        body = alarms_client.get("/api/scheduler/executions").json()

        assert isinstance(body["executions"], list)

    def test_statistics_and_running_jobs(self, alarms_client):
        create_job(alarms_client)

        assert alarms_client.get("/api/scheduler/statistics").status_code == 200
        assert alarms_client.get("/api/scheduler/running").status_code == 200


class TestSchedulerJobTypes:
    """The trigger types the scheduler advertises."""

    def test_create_cron_job(self, alarms_client):
        job_id = create_job(alarms_client, trigger_type="cron", cron_expression="*/15 * * * *")

        assert alarms_client.get(f"/api/scheduler/jobs/{job_id}").json()["job"]["trigger_type"] == "cron"

    def test_create_interval_job(self, alarms_client):
        job_id = create_job(
            alarms_client, trigger_type="interval", cron_expression=None, interval_minutes=30
        )

        job = alarms_client.get(f"/api/scheduler/jobs/{job_id}").json()["job"]
        assert job["trigger_type"] == "interval"

    def test_create_one_time_job(self, alarms_client):
        job_id = create_job(
            alarms_client, trigger_type="date", cron_expression=None,
            run_date="2030-01-01T09:00:00",
        )

        assert alarms_client.get(f"/api/scheduler/jobs/{job_id}").json()["job"]["trigger_type"] == "date"


class TestCompleteWorkflows:
    """The lifecycles end to end."""

    def test_alarm_lifecycle(self, alarms_client):
        alarm_id = create_alarm(alarms_client, name="Lifecycle")

        assert alarms_client.get(f"/api/alarms/{alarm_id}").json()["alarm"]["name"] == "Lifecycle"
        assert alarms_client.post(f"/api/alarms/{alarm_id}/enable").status_code == 200
        assert alarms_client.put(
            f"/api/alarms/{alarm_id}", json={"threshold": 20.0}
        ).status_code == 200
        assert alarms_client.get(f"/api/alarms/{alarm_id}").json()["alarm"]["threshold"] == 20.0
        assert alarms_client.delete(f"/api/alarms/{alarm_id}").status_code == 200
        assert alarms_client.get(f"/api/alarms/{alarm_id}").status_code == 404

    def test_scheduler_job_lifecycle(self, alarms_client):
        job_id = create_job(alarms_client, name="Lifecycle", enabled=True)

        assert alarms_client.get(f"/api/scheduler/jobs/{job_id}").json()["job"]["name"] == "Lifecycle"
        assert alarms_client.post(f"/api/scheduler/jobs/{job_id}/pause").status_code == 200
        assert alarms_client.post(f"/api/scheduler/jobs/{job_id}/resume").status_code == 200
        assert alarms_client.delete(f"/api/scheduler/jobs/{job_id}").status_code == 200
        assert alarms_client.get(f"/api/scheduler/jobs/{job_id}").status_code == 404

    def test_an_alarm_and_a_job_coexist(self, alarms_client):
        """The old integration test posted to two non-routes and asserted 404."""
        alarm_id = create_alarm(alarms_client, name="Coexist")
        job_id = create_job(alarms_client, name="Coexist")

        assert alarms_client.get(f"/api/alarms/{alarm_id}").status_code == 200
        assert alarms_client.get(f"/api/scheduler/jobs/{job_id}").status_code == 200


class TestLiteralRoutesAreNotShadowed:
    """`/alarms/{alarm_id}` must be declared after every literal /alarms/... route.

    FastAPI matches in declaration order. While the parameterised route came
    first, `/alarms/events` and `/alarms/statistics` resolved to it with
    "events" and "statistics" taken as alarm ids, so both documented endpoints
    answered 404 -- and the tests covering them accepted 404, so the repo
    reported them working for as long as they existed.
    """

    def test_events_is_not_taken_for_an_alarm_id(self, alarms_client):
        response = alarms_client.get("/api/alarms/events")

        assert response.status_code == 200, response.text
        assert "events" in response.json()

    def test_statistics_is_not_taken_for_an_alarm_id(self, alarms_client):
        response = alarms_client.get("/api/alarms/statistics")

        assert response.status_code == 200, response.text
        assert "statistics" in response.json()

    def test_a_real_alarm_id_still_resolves(self, alarms_client):
        """The reorder must not cost the lookup it was competing with."""
        alarm_id = create_alarm(alarms_client, name="Still findable")

        body = alarms_client.get(f"/api/alarms/{alarm_id}").json()

        assert body["alarm"]["name"] == "Still findable"
