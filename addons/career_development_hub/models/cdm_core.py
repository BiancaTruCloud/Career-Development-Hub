from dateutil.relativedelta import relativedelta

from odoo import api, fields, models


class CdmProficiencyLevel(models.Model):
    _name = "cdm.proficiency.level"
    _description = "Proficiency Level"
    _order = "sequence, id"

    name = fields.Char(required=True)
    sequence = fields.Integer(required=True, index=True)
    description = fields.Text()

    _sql_constraints = [
        ("cdm_proficiency_sequence_unique", "unique(sequence)", "Sequence must be unique."),
    ]


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    default_skill_expiry_months = fields.Integer(default=12, config_parameter="cdm.default_skill_expiry_months")
    require_manager_verification_for_soft_skills = fields.Boolean(
        config_parameter="cdm.require_manager_verification_for_soft_skills"
    )
    course_cost_hr_threshold = fields.Float(config_parameter="cdm.course_cost_hr_threshold")
    enable_skill_expiry = fields.Boolean(default=True, config_parameter="cdm.enable_skill_expiry")
    allow_assessment_downgrade = fields.Boolean(default=False, config_parameter="cdm.allow_assessment_downgrade")


class CdmCoreMixin(models.AbstractModel):
    _name = "cdm.core.mixin"
    _description = "Core utility methods for CDM"

    @api.model
    def cdm_score_to_level(self, score, scoring_rule=None):
        if scoring_rule:
            for line in scoring_rule.line_ids.sorted("min_score"):
                if line.min_score <= score <= line.max_score:
                    return line.level_id
        level = self.env["cdm.proficiency.level"].search([
            ("sequence", "<=", int(score // 20) + 1)
        ], order="sequence desc", limit=1)
        return level

    @api.model
    def cdm_get_expiry_date(self, base_date=None):
        params = self.env["ir.config_parameter"].sudo()
        if params.get_param("cdm.enable_skill_expiry", default="True") != "True":
            return False
        months = int(params.get_param("cdm.default_skill_expiry_months", default="12"))
        start = fields.Date.to_date(base_date) if base_date else fields.Date.today()
        return start + relativedelta(months=months)

    @api.model
    def cdm_is_expired(self, expires_on):
        if not expires_on:
            return False
        enabled = self.env["ir.config_parameter"].sudo().get_param("cdm.enable_skill_expiry", default="True") == "True"
        return enabled and expires_on < fields.Date.today()
