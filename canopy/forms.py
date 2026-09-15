"""WTForms definitions. Validation messages are written for the person at the keyboard."""

from __future__ import annotations

from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed, FileField
from wtforms import (
    DateField,
    IntegerField,
    SelectField,
    SelectMultipleField,
    StringField,
    TextAreaField,
)
from wtforms.validators import DataRequired, Length, NumberRange, Optional, Regexp
from wtforms.widgets import CheckboxInput, ListWidget

from .models import (
    TASKS,
    Container,
    Expression,
    GroupStatus,
    PlantSize,
    PlantStatus,
    SeedType,
    SpaceStage,
)


def _choices(enum_cls, blank: str | None = None):
    items = [(e.value, e.value.capitalize()) for e in enum_cls]
    return ([("", blank)] + items) if blank else items


class SpaceForm(FlaskForm):
    name = StringField("Name", validators=[DataRequired(), Length(max=80)])
    stage = SelectField("Stage", choices=_choices(SpaceStage), default="flowering")
    also_hosts = SelectMultipleField("Also used for", choices=_choices(SpaceStage))
    capacity = IntegerField(
        "Plants it holds", validators=[DataRequired(), NumberRange(min=1, max=10_000)], default=1
    )
    notes = TextAreaField("Notes", validators=[Optional()])


class StrainForm(FlaskForm):
    name = StringField("Name", validators=[DataRequired(), Length(max=120)])
    breeder = StringField("Breeder", validators=[Optional(), Length(max=120)])
    lineage = StringField("Lineage", validators=[Optional(), Length(max=255)])
    seed_type = SelectField("Seed type", choices=_choices(SeedType), default="regular")
    flower_days = IntegerField(
        "Flower days", validators=[DataRequired(), NumberRange(min=1, max=365)], default=70
    )
    seeds_on_hand = IntegerField(
        "Seeds on hand", validators=[Optional(), NumberRange(min=0, max=100_000)], default=0
    )
    size = SelectField("Plant size", choices=_choices(PlantSize), default="medium")
    expression = SelectField(
        "Expression", choices=_choices(Expression, blank="Unknown"), validators=[Optional()]
    )
    notes = TextAreaField("Notes", validators=[Optional()])


class GroupForm(FlaskForm):
    number = IntegerField("Group number", validators=[DataRequired(), NumberRange(min=0, max=9999)])
    name = StringField("Name (optional)", validators=[Optional(), Length(max=120)])
    space_id = SelectField("Flowering space", coerce=int, validators=[Optional()])
    flower_start = DateField("Flower start", validators=[Optional()])
    flower_days = IntegerField(
        "Flower days", validators=[DataRequired(), NumberRange(min=1, max=365)], default=70
    )
    status = SelectField("Status", choices=_choices(GroupStatus), default="planned")
    color = StringField(
        "Colour",
        validators=[
            Optional(),
            Regexp(r"^#[0-9a-fA-F]{6}$", message="Use a hex colour like #66bb6a"),
        ],
    )
    notes = TextAreaField("Notes", validators=[Optional()])


class PlantForm(FlaskForm):
    label = StringField("Label", validators=[DataRequired(), Length(max=120)])
    strain = StringField("Strain", validators=[DataRequired(), Length(max=120)])
    lineage = StringField("Lineage", validators=[Optional(), Length(max=255)])
    parent_id = SelectField("Taken from", coerce=int, validators=[Optional()])
    group_id = SelectField("Group", coerce=int, validators=[Optional()])
    space_id = SelectField("Location", coerce=int, validators=[Optional()])
    # Most plants are added the day they start: from seed, or as a cutting. "Take a
    # cutting" overrides this to clone.
    status = SelectField("Status", choices=_choices(PlantStatus), default="seedling")
    container = SelectField(
        "Container",
        choices=[("", "— not recorded —"), *_choices(Container)],
        validators=[Optional()],
    )
    started_on = DateField("Started on", validators=[Optional()])
    ended_on = DateField("Ended on", validators=[Optional()])
    end_reason = StringField("End reason", validators=[Optional(), Length(max=255)])
    notes = TextAreaField("Notes", validators=[Optional()])


class KillPlantForm(FlaskForm):
    ended_on = DateField("Date", validators=[DataRequired()])
    end_reason = StringField("Reason", validators=[Optional(), Length(max=255)])


class HarvestForm(FlaskForm):
    plant_id = SelectField(
        "Plant (optional — leave blank for whole group)", coerce=int, validators=[Optional()]
    )
    harvested_on = DateField("Harvest date", validators=[DataRequired()])
    notes = TextAreaField("Notes", validators=[Optional()])


class TaskField(SelectMultipleField):
    widget = ListWidget(prefix_label=False)
    option_widget = CheckboxInput()


class JournalForm(FlaskForm):
    entry_date = DateField("Date", validators=[DataRequired()])
    space_id = SelectField("Space", coerce=int, validators=[Optional()])
    tasks = TaskField("Done today", choices=list(TASKS.items()), validators=[Optional()])
    photo = FileField(
        "Photo",
        validators=[
            Optional(),
            FileAllowed(["jpg", "jpeg", "png", "webp", "gif", "heic"], "Images only, please."),
        ],
    )
    title = StringField("Title", validators=[Optional(), Length(max=160)])
    body = TextAreaField("Entry", validators=[Optional()])

    def validate(self, extra_validators=None) -> bool:
        ok = super().validate(extra_validators)
        # Journal entries are free-form notes, so nothing in particular is required —
        # only that the entry says *something*.
        has_photo = bool(getattr(self.photo, "data", None) and self.photo.data.filename)
        if ok and not (self.title.data or self.tasks.data or self.body.data or has_photo):
            self.title.errors = list(self.title.errors) + [
                "Tick a task, add a photo, or write a title or a note."
            ]
            return False
        return ok

    @property
    def tasks_csv(self) -> str | None:
        return ",".join(self.tasks.data) if self.tasks.data else None

    @property
    def derived_title(self) -> str:
        """Title, else the ticked tasks, else a plain label — never empty."""
        if self.title.data:
            return self.title.data
        if self.tasks.data:
            return ", ".join(TASKS[k] for k in self.tasks.data)
        if getattr(self.photo, "data", None) and self.photo.data.filename:
            return "Photo"
        return "Note"


class QuickLogForm(JournalForm):
    """Journal entry logged against one space, straight from the dashboard."""


class TakeCuttingsForm(FlaskForm):
    """Take several cuttings off one plant in a single pass."""

    count = IntegerField(
        "How many", validators=[DataRequired(), NumberRange(min=1, max=200)], default=2
    )
    space_id = SelectField("Into", coerce=int, validators=[Optional()])
    taken_on = DateField("Taken on", validators=[DataRequired()])


class MoveForm(FlaskForm):
    space_id = SelectField("Move to", coerce=int, validators=[DataRequired()])


class ImportForm(FlaskForm):
    payload = TextAreaField("JSON", validators=[DataRequired()])
