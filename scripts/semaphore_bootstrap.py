#!/usr/bin/env python3
"""Seed/update Semaphore task templates from semaphore/templates.json.

Works both ways:
  1. Locally:  SEMAPHORE_URL=... SEMAPHORE_TOKEN=... SEMAPHORE_PROJECT_ID=1 \
                python3 scripts/semaphore_bootstrap.py [--dry-run]
  2. From Semaphore UI as App=Python template pointing at this file:
                script gets survey vars as CLI args `key=value`
                (e.g. `token=xxx project_id=1`), plus env from Variable Groups.

Only stdlib, no pip deps. Idempotent: matches by template `name`,
creates missing via POST, updates existing via PUT.

API verified against semaphore develop api-docs.yml (v2.16.x):
  GET  /api/project/{id}/inventory?sort=name&order=asc      (singular!)
  GET  /api/project/{id}/environment?sort=name&order=asc    (singular!)
  GET  /api/project/{id}/repositories?sort=name&order=asc   (plural)
  GET  /api/project/{id}/templates?sort=name&order=asc      (plural)
  GET  /api/project/{id}/views                             (no sort params)
  POST /api/project/{id}/templates            -> 201 Template
  PUT  /api/project/{id}/templates/{tid}       -> 204 empty
  POST /api/project/{id}/views                 -> 201 View

Views (tabs) are declared per template via `view` name in templates.json
and auto-created when missing. Templates without `view` stay in "All".

Environments (variable groups) are resolved by name and auto-created empty
when missing — except names in STRICT_ENVIRONMENTS (currently
`service_vars`), which must be created manually since they hold secrets
only a human knows. Default group comes from templates.json `defaults`.
Optional `environments_seed` in templates.json pre-fills non-secret JSON
values once, at creation time only (re-runs never touch existing groups;
secrets are never seeded — public repo).
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

TIMEOUT = 15


def parse_kv_args(argv):
    """Semaphore Python templates pass survey vars as `key=value` args."""
    out = {}
    for arg in argv:
        if arg.startswith("--"):
            continue
        if "=" in arg:
            key, val = arg.split("=", 1)
            out[key.strip()] = val
    return out


def api_request(method, url, token, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Accept", "application/json")
    req.add_header("Authorization", "Bearer " + token)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            body = resp.read().decode("utf-8", "replace")
            status = resp.status
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:500]
        raise RuntimeError(f"{method} {url} -> HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"{method} {url} -> connection error: {exc}") from exc
    if not body.strip():
        return status, None
    try:
        return status, json.loads(body)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"{method} {url} -> invalid JSON response") from exc


def api_get_list(base, project_id, token, resource):
    url = f"{base}/project/{project_id}/{resource}?sort=name&order=asc"
    _, data = api_request("GET", url, token)
    if not isinstance(data, list):
        raise RuntimeError(f"GET {url} -> expected JSON list, got {type(data).__name__}")
    return data


def api_get_views(base, project_id, token):
    url = f"{base}/project/{project_id}/views"
    _, data = api_request("GET", url, token)
    if not isinstance(data, list):
        raise RuntimeError(f"GET {url} -> expected JSON list, got {type(data).__name__}")
    return data


def ensure_view(base, project_id, token, views, title, dry_run):
    """Return view id by title, creating the view when missing."""
    for view in views:
        if view.get("title") == title:
            return view["id"]
    known = ", ".join(sorted(str(v.get("title")) for v in views)) or "(empty)"
    if dry_run:
        if title not in _dry_announced:
            print(f'[dry-run] would create view "{title}" (known: {known})')
            _dry_announced.add(title)
        return None
    positions = [v.get("position", 0) for v in views if isinstance(v.get("position"), int)]
    position = (max(positions) + 1) if positions else 0
    print(f'[create view] "{title}"')
    _, created = api_request("POST", f"{base}/project/{project_id}/views", token,
                             {"project_id": project_id, "title": title, "position": position})
    if not isinstance(created, dict) or "id" not in created:
        raise RuntimeError(f'POST view "{title}" returned no id')
    views.append(created)
    return created["id"]


_dry_announced = set()
_dry_announced_env = set()

# Environments in this set are never auto-created: they carry secrets
# only a human knows. Everything else is created empty on demand.
STRICT_ENVIRONMENTS = {"service_vars"}


def build_seed_put_body(project_id, env_id, name, seed_json):
    """Build the PUT body that pre-fills a freshly created group with seed JSON.

    Pure helper (no network) so the create-only seed logic is unit-testable.
    `secrets` is always empty: secrets are never seeded from a public repo,
    and an empty list is a no-op for existing secrets server-side.
    """
    return {
        "id": env_id,
        "project_id": project_id,
        "name": name,
        "json": json.dumps(seed_json),
        "secrets": [],
    }


def ensure_environment(base, project_id, token, environments, name, dry_run, seed_json=None):
    """Return environment id by name, auto-creating missing groups.

    Groups hold no content at creation time, so creating them is safe.
    STRICT_ENVIRONMENTS must exist beforehand (they hold secrets).
    When `seed_json` (dict) is given and the group is created now, the seed
    is written once via PUT. Existing groups are never modified (create-only).
    """
    for env in environments:
        if env.get("name") == name:
            return env["id"]
    if name in STRICT_ENVIRONMENTS:
        known = ", ".join(sorted(str(i.get("name")) for i in environments)) or "(empty)"
        raise RuntimeError(f'Environment "{name}" not found in project. Known: {known}')
    known = ", ".join(sorted(str(i.get("name")) for i in environments)) or "(empty)"
    if dry_run:
        if name not in _dry_announced_env:
            if seed_json:
                keys = ", ".join(sorted(seed_json)) or "(empty json)"
                print(f'[dry-run] would create environment "{name}" with seed json keys ({keys}) (known: {known})')
            else:
                print(f'[dry-run] would create environment "{name}" (known: {known})')
            _dry_announced_env.add(name)
        return None
    print(f'[create environment] "{name}"')
    _, created = api_request("POST", f"{base}/project/{project_id}/environment", token,
                             {"project_id": project_id, "name": name})
    if not isinstance(created, dict) or "id" not in created:
        raise RuntimeError(f'POST environment "{name}" returned no id')
    environments.append(created)
    if seed_json:
        print(f'[seed environment] "{name}" json keys ({", ".join(sorted(seed_json))})')
        api_request("PUT", f"{base}/project/{project_id}/environment/{created['id']}", token,
                    build_seed_put_body(project_id, created["id"], name, seed_json))
    return created["id"]


def name_to_id(items, name, kind):
    for item in items:
        if item.get("name") == name:
            return item["id"]
    known = ", ".join(sorted(str(i.get("name")) for i in items)) or "(empty)"
    raise RuntimeError(f'{kind} "{name}" not found in project. Known: {known}')


def build_payload(project_id, tpl, ids):
    payload = {
        "project_id": project_id,
        "inventory_id": ids["inventory"],
        "repository_id": ids["repository"],
        "environment_id": ids["environment"],
        "name": tpl["name"],
        "app": tpl.get("app", "ansible"),
        "playbook": tpl["playbook"],
        "description": tpl.get("description", ""),
        "arguments": "[]",
        "survey_vars": tpl.get("survey_vars", []),
    }
    if ids.get("view") is not None:
        payload["view_id"] = ids["view"]
    return payload


def payload_matches(current, payload):
    """True when the existing template already equals the wanted payload.

    API nulls are treated as empty string/list so a missing optional field
    does not force an update on every run.
    """
    for key, want in payload.items():
        got = current.get(key)
        if got is None and isinstance(want, str):
            got = ""
        elif got is None and isinstance(want, list):
            got = []
        if got != want:
            return False
    return True


def validate_spec(wanted):
    """Fail fast on malformed templates.json entries (before any API PUT)."""
    seen = set()
    for tpl in wanted:
        if not isinstance(tpl, dict):
            raise RuntimeError("each template must be an object")
        name = tpl.get("name")
        if not name or not isinstance(name, str):
            raise RuntimeError("each template must have a non-empty string `name`")
        if name in seen:
            raise RuntimeError(f'duplicate template name "{name}" in templates.json')
        seen.add(name)
        if not tpl.get("playbook") or not isinstance(tpl.get("playbook"), str):
            raise RuntimeError(f'template "{name}" must have a non-empty string `playbook`')
        survey = tpl.get("survey_vars", [])
        if not isinstance(survey, list):
            raise RuntimeError(f'template "{name}": `survey_vars` must be a list')
        survey_seen = set()
        for item in survey:
            if not isinstance(item, dict) or not item.get("name"):
                raise RuntimeError(f'template "{name}": each survey_var must have a `name`')
            if item["name"] in survey_seen:
                raise RuntimeError(f'template "{name}": duplicate survey_var "{item["name"]}"')
            survey_seen.add(item["name"])
            if item.get("type") == "enum" and not item.get("values"):
                raise RuntimeError(f'template "{name}": enum survey_var "{item["name"]}" must have `values`')


def main():
    kv = parse_kv_args(sys.argv[1:])
    script_dir = os.path.dirname(os.path.abspath(__file__))
    default_templates = os.path.normpath(os.path.join(script_dir, "..", "semaphore", "templates.json"))

    parser = argparse.ArgumentParser(description="Seed Semaphore templates from JSON")
    parser.add_argument("--url", default=kv.get("url") or os.environ.get("SEMAPHORE_URL", "http://localhost:3000/api"))
    parser.add_argument("--token", default=kv.get("token") or os.environ.get("SEMAPHORE_TOKEN", ""))
    parser.add_argument("--project-id", default=kv.get("project_id") or kv.get("project-id") or os.environ.get("SEMAPHORE_PROJECT_ID", ""))
    parser.add_argument("--templates", default=kv.get("templates") or os.environ.get("SEMAPHORE_TEMPLATES", default_templates))
    parser.add_argument("--inventory", default=kv.get("inventory") or os.environ.get("SEMAPHORE_INVENTORY", ""))
    parser.add_argument("--repository", default=kv.get("repository") or os.environ.get("SEMAPHORE_REPOSITORY", ""))
    parser.add_argument("--environment", default=kv.get("environment") or os.environ.get("SEMAPHORE_ENVIRONMENT", ""))
    parser.add_argument("--dry-run", action="store_true", default=(kv.get("dry_run", "").lower() == "true"))
    # parse_known_args: Semaphore Python-шаблоны передают survey vars
    # позиционными `key=value`, их уже разобрал parse_kv_args выше.
    args, _ = parser.parse_known_args()

    base = args.url.rstrip("/")
    token = args.token.strip()
    if not token:
        print("ERROR: token is required (survey var `token` or SEMAPHORE_TOKEN env)", file=sys.stderr)
        return 1
    try:
        project_id = int(str(args.project_id).strip())
    except ValueError:
        print("ERROR: project_id is required (survey var `project_id` or SEMAPHORE_PROJECT_ID env)", file=sys.stderr)
        return 1

    try:
        with open(args.templates, encoding="utf-8") as fh:
            spec = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: cannot read templates {args.templates}: {exc}", file=sys.stderr)
        return 1
    defaults = spec.get("defaults", {})
    wanted = spec.get("templates", [])
    if not wanted:
        print(f"ERROR: no templates in {args.templates}", file=sys.stderr)
        return 1
    try:
        validate_spec(wanted)
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    env_seeds = spec.get("environments_seed", {})
    if not isinstance(env_seeds, dict):
        print(f"ERROR: environments_seed must be an object in {args.templates}", file=sys.stderr)
        return 1
    for seed_name, seed_spec in env_seeds.items():
        if not isinstance(seed_spec, dict) or not isinstance(seed_spec.get("json", {}), dict):
            print(f'ERROR: environments_seed["{seed_name}"] must be {{"json": {{...}}}} in {args.templates}',
                  file=sys.stderr)
            return 1

    default_inventory = args.inventory or defaults.get("inventory", "prod_inventory")
    default_repository = args.repository or defaults.get("repository", "ansible")
    default_environment = args.environment or defaults.get("environment", "prod_vars")

    try:
        inventories = api_get_list(base, project_id, token, "inventory")
        repositories = api_get_list(base, project_id, token, "repositories")
        environments = api_get_list(base, project_id, token, "environment")
        views = api_get_views(base, project_id, token)
        existing = api_get_list(base, project_id, token, "templates")
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    existing_by_name = {t.get("name"): t for t in existing}

    created, updated, unchanged, would_create, would_update = 0, 0, 0, 0, 0
    for tpl in wanted:
        name = tpl["name"]
        try:
            view_name = tpl.get("view", defaults.get("view"))
            view_id = (ensure_view(base, project_id, token, views, view_name, args.dry_run)
                       if view_name else None)
            env_name = tpl.get("environment", default_environment)
            env_seed = (env_seeds.get(env_name) or {}).get("json")
            ids = {
                "inventory": name_to_id(inventories, tpl.get("inventory", default_inventory), "Inventory"),
                "repository": name_to_id(repositories, tpl.get("repository", default_repository), "Repository"),
                "environment": ensure_environment(base, project_id, token, environments,
                                                  env_name, args.dry_run, env_seed),
                "view": view_id,
            }
        except RuntimeError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1
        payload = build_payload(project_id, tpl, ids)
        current = existing_by_name.get(name)
        try:
            if current is None:
                if args.dry_run:
                    print(f"[would create] {name} ({tpl['playbook']})")
                    would_create += 1
                else:
                    print(f"[create] {name} ({tpl['playbook']})")
                    api_request("POST", f"{base}/project/{project_id}/templates", token, payload)
                    created += 1
            else:
                if "id" not in current:
                    raise RuntimeError(f'Template "{name}" has no id')
                payload["id"] = current["id"]
                if payload_matches(current, payload):
                    print(f"[unchanged] {name} (id={current['id']})")
                    unchanged += 1
                elif args.dry_run:
                    print(f"[would update] {name} (id={current['id']}, {tpl['playbook']})")
                    would_update += 1
                else:
                    print(f"[update] {name} (id={current['id']}, {tpl['playbook']})")
                    # PUT требует id в body, равный id в URL (иначе 400).
                    api_request("PUT", f"{base}/project/{project_id}/templates/{current['id']}", token, payload)
                    updated += 1
        except RuntimeError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1

    print(f"done: created={created} updated={updated} unchanged={unchanged} "
          f"would_create={would_create} would_update={would_update} dry_run={args.dry_run}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
