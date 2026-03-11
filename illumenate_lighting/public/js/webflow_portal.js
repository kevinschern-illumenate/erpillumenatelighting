/**
 * Webflow Portal Integration JavaScript
 *
 * Client-side code for embedding on Webflow pages to handle:
 * - Authentication (login/logout against ERPNext)
 * - Dealer-gated pricing visibility
 * - Project → Fixture Schedule → Line ID cascading selection
 * - Adding configured fixtures to schedules
 *
 * Usage:
 *   Include this script on Webflow pages and configure ERPNEXT_URL.
 *   Call IllumenatePortal.init({ erpnextUrl: "https://your-erpnext.com" })
 *   on page load.
 */

/* exported IllumenatePortal */
var IllumenatePortal = (function () {
    "use strict";

    // --------------- Configuration ---------------
    var config = {
        erpnextUrl: "",
        storageKeyPrefix: "ill_portal_",
    };

    // --------------- State ---------------
    var state = {
        user: null,
        apiKey: null,
        apiSecret: null,
        isDealer: false,
        customer: null,
        projects: [],
        schedules: [],
        lines: [],
    };

    // --------------- Storage helpers ---------------
    function _storageKey(key) {
        return config.storageKeyPrefix + key;
    }

    function _save(key, value) {
        try {
            sessionStorage.setItem(_storageKey(key), JSON.stringify(value));
        } catch (e) {
            // sessionStorage not available
        }
    }

    function _load(key) {
        try {
            var raw = sessionStorage.getItem(_storageKey(key));
            return raw ? JSON.parse(raw) : null;
        } catch (e) {
            return null;
        }
    }

    function _clear() {
        try {
            var keys = Object.keys(sessionStorage);
            for (var i = 0; i < keys.length; i++) {
                if (keys[i].indexOf(config.storageKeyPrefix) === 0) {
                    sessionStorage.removeItem(keys[i]);
                }
            }
        } catch (e) {
            // sessionStorage not available
        }
    }

    // --------------- API helpers ---------------
    function _apiCall(method, params) {
        var url = config.erpnextUrl + "/api/method/" + method;
        var headers = {
            "Content-Type": "application/json",
            Accept: "application/json",
        };

        if (state.apiKey && state.apiSecret) {
            headers["Authorization"] = "token " + state.apiKey + ":" + state.apiSecret;
        }

        return fetch(url, {
            method: "POST",
            headers: headers,
            credentials: "include",
            body: JSON.stringify(params || {}),
        }).then(function (resp) {
            if (!resp.ok) {
                throw new Error("API request failed: " + resp.status);
            }
            return resp.json();
        }).then(function (data) {
            return data.message || data;
        });
    }

    // --------------- Auth ---------------
    function login(usr, pwd) {
        var url = config.erpnextUrl + "/api/method/login";
        return fetch(url, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            credentials: "include",
            body: JSON.stringify({ usr: usr, pwd: pwd }),
        })
            .then(function (resp) {
                if (!resp.ok) throw new Error("Login failed");
                return resp.json();
            })
            .then(function () {
                return _apiCall(
                    "illumenate_lighting.illumenate_lighting.api.webflow_auth.get_user_context"
                );
            })
            .then(function (ctx) {
                if (!ctx.success) throw new Error(ctx.error || "Context fetch failed");
                state.user = ctx.user;
                state.apiKey = ctx.api_key;
                state.apiSecret = ctx.api_secret;
                state.isDealer = ctx.is_dealer;
                state.customer = ctx.customer;
                _save("auth", {
                    user: ctx.user,
                    apiKey: ctx.api_key,
                    apiSecret: ctx.api_secret,
                    isDealer: ctx.is_dealer,
                    customer: ctx.customer,
                    customerName: ctx.customer_name,
                });
                _updatePricingVisibility();
                return ctx;
            });
    }

    function logout() {
        state.user = null;
        state.apiKey = null;
        state.apiSecret = null;
        state.isDealer = false;
        state.customer = null;
        _clear();
        _updatePricingVisibility();
        return _apiCall("logout").catch(function () {
            /* ignore logout errors */
        });
    }

    function restoreSession() {
        var auth = _load("auth");
        if (auth && auth.user) {
            state.user = auth.user;
            state.apiKey = auth.apiKey;
            state.apiSecret = auth.apiSecret;
            state.isDealer = auth.isDealer;
            state.customer = auth.customer;
            _updatePricingVisibility();
            return true;
        }
        return false;
    }

    // --------------- Pricing visibility ---------------
    function _updatePricingVisibility() {
        var pricingEls = document.querySelectorAll("[data-dealer-pricing]");
        for (var i = 0; i < pricingEls.length; i++) {
            pricingEls[i].style.display = state.isDealer ? "" : "none";
        }
    }

    function fetchPricing(itemCode, targetEl) {
        if (!state.isDealer) return Promise.resolve(null);
        return _apiCall(
            "illumenate_lighting.illumenate_lighting.api.webflow_portal.get_pricing",
            { item_code: itemCode }
        ).then(function (result) {
            if (result.success && result.price !== null && targetEl) {
                targetEl.textContent = result.currency + " " + result.price.toFixed(2);
                targetEl.style.display = "";
            }
            return result;
        });
    }

    // --------------- Cascading selection ---------------
    function loadProjects() {
        return _apiCall(
            "illumenate_lighting.illumenate_lighting.api.webflow_portal.get_projects"
        ).then(function (result) {
            state.projects = result.success ? result.projects : [];
            return state.projects;
        });
    }

    function loadSchedules(projectName) {
        return _apiCall(
            "illumenate_lighting.illumenate_lighting.api.webflow_portal.get_fixture_schedules",
            { project: projectName }
        ).then(function (result) {
            state.schedules = result.success ? result.schedules : [];
            return state.schedules;
        });
    }

    function loadLines(projectName, scheduleName) {
        return _apiCall(
            "illumenate_lighting.illumenate_lighting.api.webflow_portal.get_line_ids",
            { project: projectName, fixture_schedule: scheduleName }
        ).then(function (result) {
            state.lines = result.success ? result.lines : [];
            return state.lines;
        });
    }

    function addFixture(projectName, scheduleName, partNumber, lineId, overwrite) {
        return _apiCall(
            "illumenate_lighting.illumenate_lighting.api.webflow_portal.add_fixture_to_schedule",
            {
                project: projectName,
                fixture_schedule: scheduleName,
                fixture_part_number: partNumber,
                line_id: lineId || "",
                overwrite: overwrite ? "1" : "0",
            }
        );
    }

    // --------------- Dropdown population helpers ---------------
    function _populateSelect(selectEl, items, valueFn, labelFn) {
        if (!selectEl) return;
        selectEl.innerHTML = '<option value="">— Select —</option>';
        for (var i = 0; i < items.length; i++) {
            var opt = document.createElement("option");
            opt.value = valueFn(items[i]);
            opt.textContent = labelFn(items[i]);
            selectEl.appendChild(opt);
        }
    }

    function bindCascadingDropdowns(opts) {
        var projectSelect = document.querySelector(opts.projectSelector || "#ill-project-select");
        var scheduleSelect = document.querySelector(opts.scheduleSelector || "#ill-schedule-select");
        var lineSelect = document.querySelector(opts.lineSelector || "#ill-line-select");

        if (projectSelect) {
            loadProjects().then(function (projects) {
                _populateSelect(
                    projectSelect,
                    projects,
                    function (p) { return p.name; },
                    function (p) { return p.project_name; }
                );
            });

            projectSelect.addEventListener("change", function () {
                var val = projectSelect.value;
                if (scheduleSelect) scheduleSelect.innerHTML = '<option value="">— Select —</option>';
                if (lineSelect) lineSelect.innerHTML = '<option value="">— Select —</option>';
                if (!val) return;
                loadSchedules(val).then(function (schedules) {
                    _populateSelect(
                        scheduleSelect,
                        schedules,
                        function (s) { return s.name; },
                        function (s) { return s.schedule_name + " (" + s.status + ")"; }
                    );
                });
            });
        }

        if (scheduleSelect) {
            scheduleSelect.addEventListener("change", function () {
                var projVal = projectSelect ? projectSelect.value : "";
                var schedVal = scheduleSelect.value;
                if (lineSelect) lineSelect.innerHTML = '<option value="">— Select —</option>';
                if (!projVal || !schedVal) return;
                loadLines(projVal, schedVal).then(function (lines) {
                    _populateSelect(
                        lineSelect,
                        lines,
                        function (l) { return l.line_id; },
                        function (l) {
                            var label = l.line_id;
                            if (l.fixture_part_number) label += " — " + l.fixture_part_number;
                            return label;
                        }
                    );
                });
            });
        }
    }

    // --------------- Init ---------------
    function init(opts) {
        if (opts && opts.erpnextUrl) {
            config.erpnextUrl = opts.erpnextUrl.replace(/\/+$/, "");
        }
        restoreSession();
    }

    // --------------- Public API ---------------
    return {
        init: init,
        login: login,
        logout: logout,
        restoreSession: restoreSession,
        fetchPricing: fetchPricing,
        loadProjects: loadProjects,
        loadSchedules: loadSchedules,
        loadLines: loadLines,
        addFixture: addFixture,
        bindCascadingDropdowns: bindCascadingDropdowns,
        getState: function () {
            return state;
        },
    };
})();
