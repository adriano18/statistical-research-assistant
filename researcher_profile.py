"""An optional, local researcher profile (Stage 34, part C).

One small JSON file beside the projects folder. Every field is optional and
the profile may stay empty; there is no account and nothing is uploaded.
The profile never holds e-mail addresses, institution or student IDs, or
sensitive personal data, and projects never write into it (deleting it
changes no project).

What the workspace does with it, and nothing more:

* ``experience == "experienced"`` hides the "How it works" introduction on
  Home by default (it stays available in Help);
* ``explanations == "detailed"`` opens the interpretation section of each
  result by default; ``"brief"`` keeps it closed (the default);
* ``language`` is the interface language and follows the language switch.

The study level and research field are stored for the researcher's own
reference and for a future, explicitly permitted assistant; they are never
used to judge work, to choose a statistical method or to change a result.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields, replace
import json
import os
from pathlib import Path
import re
import tempfile

FORMAT = 1
STUDY_LEVELS = ("", "bachelor", "master", "doctoral", "faculty", "other", "not_said")
EXPERIENCE = ("", "new", "some", "experienced")
EXPLANATIONS = ("", "brief", "standard", "detailed")
LANGUAGES = ("", "en", "lv", "ru")
CHOICES = {"study_level": STUDY_LEVELS, "experience": EXPERIENCE,
           "explanations": EXPLANATIONS, "language": LANGUAGES}
LIMITS = {"display_name": 80, "research_field": 120}
_EMAIL = re.compile(r"\S+@\S+\.\S+")
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


class ProfileError(ValueError):
    """A profile value that is not accepted (the message says which and why)."""


@dataclass(frozen=True)
class ResearcherProfile:
    display_name: str = ""
    study_level: str = ""
    research_field: str = ""
    experience: str = ""
    language: str = ""
    explanations: str = ""

    @property
    def empty(self) -> bool:
        return not any(asdict(self).values())


def profile_path(data_root: Path) -> Path:
    """``<data root>/profile/profile.json``; the data root also holds ``projects``."""
    return Path(data_root) / "profile" / "profile.json"


def validate(profile: ResearcherProfile) -> ResearcherProfile:
    """The profile with text trimmed; raises ProfileError for a refused value."""
    values = {}
    for item in fields(ResearcherProfile):
        value = getattr(profile, item.name)
        value = "" if value is None else str(value).strip()
        if item.name in CHOICES and value not in CHOICES[item.name]:
            raise ProfileError(f"{item.name}: {value!r} is not one of the offered choices.")
        if item.name in LIMITS:
            if len(value) > LIMITS[item.name]:
                raise ProfileError(f"{item.name}: at most {LIMITS[item.name]} characters.")
            if _CONTROL.search(value):
                raise ProfileError(f"{item.name}: line breaks and control characters are not used.")
            if _EMAIL.search(value):
                raise ProfileError(f"{item.name}: the profile does not store e-mail addresses.")
        values[item.name] = value
    return ResearcherProfile(**values)


def load_profile(path: Path) -> ResearcherProfile:
    """The saved profile; an empty one when there is none or it cannot be read.

    Unknown keys (from a newer version) and values this version does not
    offer are ignored rather than failing the start of the application."""
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ResearcherProfile()
    if not isinstance(raw, dict):
        return ResearcherProfile()
    data = raw.get("profile", raw)
    if not isinstance(data, dict):
        return ResearcherProfile()
    profile = ResearcherProfile()
    for item in fields(ResearcherProfile):
        value = data.get(item.name, "")
        if not isinstance(value, str):
            continue
        try:
            profile = validate(replace(profile, **{item.name: value}))
        except ProfileError:
            continue
    return profile


def save_profile(path: Path, profile: ResearcherProfile) -> ResearcherProfile:
    """Write the profile atomically; an empty profile removes the file."""
    profile = validate(profile)
    path = Path(path)
    if profile.empty:
        delete_profile(path)
        return profile
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps({"format": FORMAT, "profile": asdict(profile)}, ensure_ascii=False,
                      indent=1).encode("utf-8")
    fd, temp = tempfile.mkstemp(prefix=".tmp-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    except BaseException:
        Path(temp).unlink(missing_ok=True)
        raise
    return profile


def delete_profile(path: Path) -> bool:
    """Remove the profile file; True when there was one."""
    try:
        Path(path).unlink()
        return True
    except FileNotFoundError:
        return False
