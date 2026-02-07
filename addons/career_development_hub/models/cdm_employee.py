from dateutil.relativedelta import relativedelta
from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    cdm_skill_ids = fields.One2many("cdm.employee.skill", "employee_id")
    cdm_readiness_score = fields.Float(compute="_compute_cdm_readiness")
    cdm_gap_count = fields.Integer(compute="_compute_cdm_readiness")
    cdm_role_profile_id = fields.Many2one("cdm.role.profile", compute="_compute_cdm_role_profile", store=True, readonly=False)

    @api.depends("job_id", "department_id")
    def _compute_cdm_role_profile(self):
        today = fields.Date.today()
        for rec in self:
            domain = [("job_id", "=", rec.job_id.id), ("active", "=", True), "|", ("date_from", "=", False), ("date_from", "<=", today), "|", ("date_to", "=", False), ("date_to", ">=", today)]
            if rec.department_id:
                domain = domain + ["|", ("department_id", "=", False), ("department_id", "=", rec.department_id.id)]
            rec.cdm_role_profile_id = self.env["cdm.role.profile"].search(domain, limit=1, order="id desc")

    @api.depends("cdm_skill_ids.current_level_id", "cdm_role_profile_id")
    def _compute_cdm_readiness(self):
        for employee in self:
            required = employee.cdm_role_profile_id.line_ids.filtered("is_required")
            if not required:
                employee.cdm_readiness_score = 0
                employee.cdm_gap_count = 0
                continue
            achieved = 0
            gaps = 0
            by_skill = {line.skill_id.id: line for line in required}
            for line in required:
                emp_skill = employee.cdm_skill_ids.filtered(lambda s: s.skill_id == line.skill_id)[:1]
                if emp_skill and emp_skill.current_level_id.sequence >= line.target_level_id.sequence:
                    achieved += 1
                else:
                    gaps += 1
            employee.cdm_readiness_score = achieved * 100.0 / len(by_skill)
            employee.cdm_gap_count = gaps


class CdmEmployeeSkill(models.Model):
    _name = "cdm.employee.skill"
    _description = "Employee Skill"
    _inherit = ["mail.thread", "cdm.core.mixin"]

    employee_id = fields.Many2one("hr.employee", required=True, index=True)
    skill_id = fields.Many2one("cdm.skill", required=True)
    current_level_id = fields.Many2one("cdm.proficiency.level", required=True, tracking=True)
    target_level_id = fields.Many2one("cdm.proficiency.level", compute="_compute_target_level", store=True)
    override_target = fields.Boolean(default=False)
    source_type = fields.Selection(
        [("self_declared", "Self Declared"), ("assessed", "Assessed"), ("manager_verified", "Manager Verified"), ("imported", "Imported")],
        default="self_declared",
        required=True,
    )
    verification_status = fields.Selection(
        [("none", "None"), ("pending", "Pending"), ("verified", "Verified"), ("rejected", "Rejected")],
        default="none",
        tracking=True,
    )
    last_updated = fields.Datetime()
    expires_on = fields.Date()
    is_expired = fields.Boolean(compute="_compute_is_expired", store=True)
    evidence_ids = fields.One2many("cdm.skill.evidence", "employee_skill_id")
    notes = fields.Text()

    _sql_constraints = [
        ("cdm_employee_skill_uniq", "unique(employee_id, skill_id)", "This employee already has this skill."),
    ]

    @api.depends("employee_id.cdm_role_profile_id", "skill_id", "override_target")
    def _compute_target_level(self):
        for rec in self:
            if rec.override_target and rec.target_level_id:
                continue
            target = rec.employee_id.cdm_role_profile_id.line_ids.filtered(lambda l: l.skill_id == rec.skill_id)[:1]
            rec.target_level_id = target.target_level_id if target else False

    @api.depends("expires_on")
    def _compute_is_expired(self):
        for rec in self:
            rec.is_expired = rec.cdm_is_expired(rec.expires_on)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            vals["last_updated"] = fields.Datetime.now()
            if vals.get("source_type") == "assessed" and not vals.get("expires_on"):
                vals["expires_on"] = self.cdm_get_expiry_date()
        return super().create(vals_list)

    def write(self, vals):
        if "current_level_id" in vals:
            vals["last_updated"] = fields.Datetime.now()
        if vals.get("source_type") == "assessed" and not vals.get("expires_on"):
            vals["expires_on"] = self.cdm_get_expiry_date()
        if vals.get("verification_status") == "verified":
            self._check_verification_rights()
        return super().write(vals)

    def _check_verification_rights(self):
        if self.env.user.has_group("career_development_hub.group_cdm_hr_admin"):
            return
        if not self.env.user.has_group("career_development_hub.group_cdm_manager"):
            raise UserError("Only managers or HR admins can verify skills.")

    def action_request_verification(self):
        activity_type = self.env.ref("mail.mail_activity_data_todo")
        for rec in self:
            rec.verification_status = "pending"
            manager_user = rec.employee_id.parent_id.user_id
            if manager_user:
                rec.activity_schedule(
                    activity_type_id=activity_type.id,
                    user_id=manager_user.id,
                    note=f"Please verify skill {rec.skill_id.name} for {rec.employee_id.name}",
                )

    @api.constrains("verification_status", "skill_id")
    def _check_soft_skill_verification_policy(self):
        require_mgr = self.env["ir.config_parameter"].sudo().get_param(
            "cdm.require_manager_verification_for_soft_skills", default="False"
        ) == "True"
        for rec in self:
            if (
                require_mgr
                and rec.skill_id.skill_type == "soft"
                and rec.verification_status == "verified"
                and not self.env.user.has_group("career_development_hub.group_cdm_manager")
                and not self.env.user.has_group("career_development_hub.group_cdm_hr_admin")
            ):
                raise ValidationError("Only managers can verify soft skills when policy is enabled.")

    @api.model
    def cron_skill_expiry_notifier(self):
        today = fields.Date.today()
        upcoming = today + relativedelta(days=30)
        activity_type = self.env.ref("mail.mail_activity_data_todo")
        records = self.search([("expires_on", "<=", upcoming), ("expires_on", "!=", False)])
        for rec in records:
            target_users = (rec.employee_id.user_id | rec.employee_id.parent_id.user_id).filtered(lambda u: u)
            for user in target_users:
                rec.activity_schedule(
                    activity_type_id=activity_type.id,
                    user_id=user.id,
                    note=f"Skill {rec.skill_id.name} for {rec.employee_id.name} is expiring or expired on {rec.expires_on}.",
                )


class CdmSkillEvidence(models.Model):
    _name = "cdm.skill.evidence"
    _description = "Skill Evidence"

    employee_skill_id = fields.Many2one("cdm.employee.skill", required=True, ondelete="cascade")
    attachment_id = fields.Many2one("ir.attachment", required=True)
    evidence_type = fields.Selection(
        [("certificate", "Certificate"), ("project", "Project"), ("link", "Link"), ("other", "Other")],
        default="other",
        required=True,
    )
    url = fields.Char()
    uploaded_by = fields.Many2one("res.users", default=lambda self: self.env.user, readonly=True)
    uploaded_on = fields.Datetime(default=fields.Datetime.now, readonly=True)
