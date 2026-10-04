"""The web layer: routes, the token guard and the one page."""

from __future__ import annotations

OVERVIEW_SECTIONS = ("server", "system", "processes", "containers", "ports", "services")


class TestHealth:
    def test_healthz_is_open_and_says_ok(self, client):
        res = client.get("/healthz")
        assert res.status_code == 200
        body = res.json()
        assert body["status"] == "ok"
        assert body["ok"] is True
        assert body["version"]

    def test_healthz_stays_open_even_with_a_token(self, token_client):
        assert token_client.get("/healthz").status_code == 200


class TestOverview:
    def test_overview_carries_every_section(self, client):
        res = client.get("/api/overview")
        assert res.status_code == 200
        body = res.json()
        for section in OVERVIEW_SECTIONS:
            assert section in body, section
        assert body["system"]["hostname"]
        assert isinstance(body["ports"]["ports"], list)

    def test_sections_match_their_own_endpoints(self, client):
        """The two endpoints must agree on shape - values move between requests.

        A port can open or close in the milliseconds between two calls, so this
        compares structure: same keys, same internal consistency, same host.
        """
        overview = client.get("/api/overview").json()
        system = client.get("/api/system").json()
        ports = client.get("/api/ports").json()

        assert overview["system"]["hostname"] == system["hostname"]
        assert overview["ports"]["summary"]["total"] == len(overview["ports"]["ports"])
        assert ports["summary"]["total"] == len(ports["ports"])
        assert set(overview["ports"]) == set(ports)
        assert set(overview["services"]) == set(client.get("/api/services").json())
        assert set(overview["containers"]) == set(client.get("/api/docker").json())

    def test_process_limit_is_respected(self, client):
        body = client.get("/api/processes?limit=3").json()
        assert len(body["processes"]) <= 3

    def test_process_limit_is_validated(self, client):
        assert client.get("/api/processes?limit=0").status_code == 422

    def test_services_endpoint(self, client):
        body = client.get("/api/services").json()
        assert "units" in body

    def test_docker_endpoint_reports_rather_than_fails(self, client):
        res = client.get("/api/docker")
        assert res.status_code == 200
        assert "containers" in res.json()


class TestTokenGuard:
    def test_api_without_token_is_rejected(self, token_client):
        res = token_client.get("/api/overview")
        assert res.status_code == 401
        assert res.json()["ok"] is False

    def test_api_with_header_token(self, token_client):
        res = token_client.get("/api/overview", headers={"X-SM-Token": "test-token-12345"})
        assert res.status_code == 200

    def test_api_with_bearer_token(self, token_client):
        res = token_client.get(
            "/api/overview", headers={"Authorization": "Bearer test-token-12345"}
        )
        assert res.status_code == 200

    def test_api_with_query_token(self, token_client):
        assert token_client.get("/api/overview?token=test-token-12345").status_code == 200

    def test_api_with_wrong_token(self, token_client):
        res = token_client.get("/api/overview", headers={"X-SM-Token": "nope"})
        assert res.status_code == 401

    def test_no_token_configured_means_no_guard(self, client):
        assert client.get("/api/overview").status_code == 200

    def test_the_page_itself_is_not_gated(self, token_client):
        # The token is entered in the page, so the page must load without it.
        assert token_client.get("/").status_code == 200


class TestStaticPage:
    def test_index_is_served_with_assets(self, client):
        res = client.get("/")
        assert res.status_code == 200
        text = res.text
        assert "/js/app.js" in text
        assert "/css/style.css" in text
        assert "Server Manager" in text

    def test_javascript_and_css_are_reachable(self, client):
        assert client.get("/js/app.js").status_code == 200
        assert client.get("/css/style.css").status_code == 200

    def test_page_calls_only_the_overview_endpoint(self, client):
        js = client.get("/js/app.js").text
        assert "/api/overview" in js
        # No route that changes anything may be called from the page.
        for verb in ("POST", "PUT", "DELETE", "PATCH"):
            assert verb not in js


class TestSidebar:
    """Item 9: the sidebar is a client-side filter over the one overview poll."""

    def test_page_ships_a_sidebar_with_one_entry_per_view(self, client):
        text = client.get("/").text
        assert 'class="side"' in text
        for view in ("overview", "ports", "docker", "programs", "processes"):
            assert f'data-view="{view}"' in text, view
            assert f'id="view-{view}"' in text, view

    def test_every_view_holds_the_panel_it_names(self, client):
        text = client.get("/").text
        for body in ("ports-body", "docker-body", "services-body", "processes-body", "kpis"):
            assert f'id="{body}"' in text, body

    def test_only_one_view_is_visible_before_a_click(self, client):
        text = client.get("/").text
        # overview is the landing view; the other four wait behind a click
        assert text.count('class="view hidden"') == 4
        assert 'class="view" id="view-overview"' in text

    def test_switching_a_view_adds_no_request(self, client):
        js = client.get("/js/app.js").text
        assert "setView" in js and "VIEWS" in js
        # A view switch must reuse the poll, not open a second endpoint.
        assert js.count('get("/api/') == 1
        endpoints = {chunk.split('"')[0] for chunk in js.split('"/api/')[1:]}
        assert endpoints == {"overview"}, endpoints

    def test_sidebar_counts_are_filled_from_the_payload(self, client):
        js = client.get("/js/app.js").text
        for badge in ("nav-ports", "nav-docker", "nav-programs", "nav-processes"):
            assert badge in js, badge
        assert "renderBadges" in js
