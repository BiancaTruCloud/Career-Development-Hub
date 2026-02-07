from odoo import api, fields, models
from odoo.exceptions import ValidationError


class CdmSkillCategory(models.Model):
    _name = "cdm.skill.category"
    _description = "Skill Category"

    name = fields.Char(required=True)
    skill_type = fields.Selection([("hard", "Hard"), ("soft", "Soft"), ("both", "Both")], default="both", required=True)
    active = fields.Boolean(default=True)

    _sql_constraints = [("cdm_skill_category_name_unique", "unique(name)", "Category name must be unique.")]


class CdmSkill(models.Model):
    _name = "cdm.skill"
    _description = "Skill"

    name = fields.Char(required=True)
    external_skill_key = fields.Char(index=True, copy=False)
    skill_type = fields.Selection([("hard", "Hard"), ("soft", "Soft")], required=True)
    category_id = fields.Many2one("cdm.skill.category")
    description = fields.Text()
    active = fields.Boolean(default=True)
    assessment_available = fields.Boolean(compute="_compute_availability")
    course_count = fields.Integer(compute="_compute_availability")

    _sql_constraints = [
        ("cdm_skill_name_company_uniq", "unique(name, company_id)", "Skill must be unique per company."),
        ("cdm_skill_external_key_company_uniq", "unique(external_skill_key, company_id)", "External skill key must be unique per company."),
    ]

    company_id = fields.Many2one("res.company", default=lambda self: self.env.company, required=True)

    def _compute_availability(self):
        assessment_data = self.env["cdm.assessment.skill.map"].read_group(
            [("skill_id", "in", self.ids)], ["skill_id"], ["skill_id"]
        )
        course_data = self.env["cdm.course.skill.map"].read_group(
            [("skill_id", "in", self.ids)], ["skill_id"], ["skill_id"]
        )
        assessment_map = {item["skill_id"][0]: True for item in assessment_data if item.get("skill_id")}
        course_map = {item["skill_id"][0]: item["skill_id_count"] for item in course_data if item.get("skill_id")}
        for rec in self:
            rec.assessment_available = assessment_map.get(rec.id, False)
            rec.course_count = course_map.get(rec.id, 0)


class CdmRoleProfile(models.Model):
    _name = "cdm.role.profile"
    _description = "Role Profile"

    name = fields.Char(required=True)
    external_role_id = fields.Char(index=True, copy=False)
    role_title = fields.Char()
    career_level = fields.Char()
    sector = fields.Char()
    industry = fields.Char()
    department_name = fields.Char()
    sub_department = fields.Char()
    job_family = fields.Char()
    role_description = fields.Text()
    key_responsibilities = fields.Text()
    psod_occupational_category = fields.Char()
    psod_skill_level = fields.Char()
    nqf_band = fields.Char()
    recommended_nqf_levels = fields.Char()
    sasko_major_group = fields.Char()
    sasko_skill_level = fields.Char()
    sasko_unit_group_code = fields.Char()
    import_source = fields.Char()
    last_imported_on = fields.Datetime()
    job_id = fields.Many2one("hr.job", required=True)
    department_id = fields.Many2one("hr.department")
    version = fields.Char(default="1")
    active = fields.Boolean(default=True)
    date_from = fields.Date()
    date_to = fields.Date()
    line_ids = fields.One2many("cdm.role.profile.line", "profile_id")

    _sql_constraints = [("cdm_role_profile_external_id_unique", "unique(external_role_id)", "External role ID must be unique.")]

    @api.constrains("date_from", "date_to")
    def _check_dates(self):
        for rec in self:
            if rec.date_from and rec.date_to and rec.date_to < rec.date_from:
                raise ValidationError("End date cannot be before start date.")


class CdmRoleProfileLine(models.Model):
    _name = "cdm.role.profile.line"
    _description = "Role Profile Skill Line"

    profile_id = fields.Many2one("cdm.role.profile", required=True, ondelete="cascade")
    skill_id = fields.Many2one("cdm.skill", required=True)
    target_level_id = fields.Many2one("cdm.proficiency.level", required=True)
    is_required = fields.Boolean(default=True)
    weight = fields.Float(default=1.0)

    _sql_constraints = [
        ("cdm_role_profile_skill_uniq", "unique(profile_id, skill_id)", "Skill already exists in this role profile."),
    ]
