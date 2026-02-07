from odoo import api, fields, models
from odoo.exceptions import ValidationError


class CdmAssessment(models.Model):
    _name = "cdm.assessment"
    _description = "Assessment"

    name = fields.Char(required=True)
    assessment_type = fields.Selection(
        [("survey_quiz", "Survey Quiz"), ("self_survey", "Self Survey"), ("external", "External")],
        default="survey_quiz",
        required=True,
    )
    survey_id = fields.Many2one("survey.survey")
    external_url = fields.Char()
    duration_minutes = fields.Integer()
    active = fields.Boolean(default=True)
    map_line_ids = fields.One2many("cdm.assessment.skill.map", "assessment_id")


class CdmAssessmentSkillMap(models.Model):
    _name = "cdm.assessment.skill.map"
    _description = "Assessment Skill Mapping"

    assessment_id = fields.Many2one("cdm.assessment", required=True, ondelete="cascade")
    skill_id = fields.Many2one("cdm.skill", required=True)
    max_level_id = fields.Many2one("cdm.proficiency.level")
    scoring_rule_id = fields.Many2one("cdm.scoring.rule", required=True)


class CdmScoringRule(models.Model):
    _name = "cdm.scoring.rule"
    _description = "Scoring Rule"

    name = fields.Char(required=True)
    line_ids = fields.One2many("cdm.scoring.rule.line", "rule_id")


class CdmScoringRuleLine(models.Model):
    _name = "cdm.scoring.rule.line"
    _description = "Scoring Rule Line"
    _order = "min_score"

    rule_id = fields.Many2one("cdm.scoring.rule", required=True, ondelete="cascade")
    min_score = fields.Float(required=True)
    max_score = fields.Float(required=True)
    level_id = fields.Many2one("cdm.proficiency.level", required=True)

    @api.constrains("min_score", "max_score", "rule_id")
    def _check_ranges(self):
        for rec in self:
            if rec.max_score < rec.min_score:
                raise ValidationError("Max score must be greater than or equal to min score.")
            overlap = self.search_count([
                ("rule_id", "=", rec.rule_id.id),
                ("id", "!=", rec.id),
                ("min_score", "<=", rec.max_score),
                ("max_score", ">=", rec.min_score),
            ])
            if overlap:
                raise ValidationError("Scoring ranges cannot overlap.")


class CdmAssessmentAttempt(models.Model):
    _name = "cdm.assessment.attempt"
    _description = "Assessment Attempt"
    _inherit = ["cdm.core.mixin", "mail.thread"]

    employee_id = fields.Many2one("hr.employee", required=True)
    assessment_id = fields.Many2one("cdm.assessment", required=True)
    score = fields.Float(required=True)
    awarded_level_id = fields.Many2one("cdm.proficiency.level")
    completed_on = fields.Datetime(default=fields.Datetime.now)
    state = fields.Selection([("draft", "Draft"), ("done", "Done")], default="draft", tracking=True)

    def action_apply_result(self):
        self.ensure_one()
        allow_downgrade = self.env["ir.config_parameter"].sudo().get_param("cdm.allow_assessment_downgrade", default="False") == "True"
        for mapping in self.assessment_id.map_line_ids:
            awarded = self.cdm_score_to_level(self.score, mapping.scoring_rule_id)
            if mapping.max_level_id and awarded and awarded.sequence > mapping.max_level_id.sequence:
                awarded = mapping.max_level_id
            if not awarded:
                continue
            emp_skill = self.env["cdm.employee.skill"].search([
                ("employee_id", "=", self.employee_id.id),
                ("skill_id", "=", mapping.skill_id.id),
            ], limit=1)
            vals = {
                "employee_id": self.employee_id.id,
                "skill_id": mapping.skill_id.id,
                "current_level_id": awarded.id,
                "source_type": "assessed",
                "verification_status": "verified",
                "expires_on": self.cdm_get_expiry_date(),
            }
            if not emp_skill:
                self.env["cdm.employee.skill"].create(vals)
            elif allow_downgrade or awarded.sequence >= emp_skill.current_level_id.sequence:
                emp_skill.write(vals)
        self.awarded_level_id = self.cdm_score_to_level(self.score)
        self.state = "done"
