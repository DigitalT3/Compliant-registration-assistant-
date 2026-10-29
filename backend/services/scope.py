"""Who sees which team's data: a team lead is limited to the team they lead, everyone else with analytics sees all."""
from ..errors import ApiError


# PUBLIC_INTERFACE
def lead_team(user: dict) -> str | None:
    """Return the team a team lead is limited to, or ``None`` when the user is not limited.

    A lead's team is the ``function`` of the account (the same value sessions record as ``user_group``).
    A lead without a team gets 403 rather than every team's data.
    """
    if user.get("role") != "lead":
        return None
    if not user.get("function"):
        raise ApiError(403, "team_required", "This team lead account has no team yet. Ask an administrator to assign one.")
    return user["function"]


# PUBLIC_INTERFACE
def scoped(user: dict, filters: dict) -> dict:
    """Return the filters with a lead's team forced in (a team in the request is ignored) and grouping by team removed."""
    team = lead_team(user)
    if team is None:
        return filters
    out = {**filters, "group": team}
    if out.get("group_by") == "group":
        out["group_by"] = None
    return out


# PUBLIC_INTERFACE
def not_for_leads(user: dict) -> dict:
    """Dependency body for analytics data that is not split by team (user-test baseline and interviews)."""
    if user.get("role") == "lead":
        raise ApiError(403, "forbidden", "Team leads see their own team's dashboard only.")
    return user
