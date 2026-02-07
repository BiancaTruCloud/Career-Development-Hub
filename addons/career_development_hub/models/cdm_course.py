from odoo import api, fields, models
from odoo.exceptions import ValidationError


class CdmCourse(models.Model):
    _name = "cdm.course"
    _description = "Course"

    name = fields.Char(required=True)
    provider = fields.Char()
    course_type = fields.Selection(
        [("elearning", "eLearning"), ("external", "External"), ("internal_session", "Internal Session")],
        default="external",
        required=True,
    )
    channel_id = fields.Many2one("slide.channel")
    external_url = fields.Char()
    duration_hours = fields.Float()
    cost = fields.Float()
    active = fields.Boolean(default=True)
    skill_map_ids = fields.One2many("cdm.course.skill.map", "course_id")
    approval_required = fields.Boolean(default=True)


class CdmCourseSkillMap(models.Model):
    _name = "cdm.course.skill.map"
    _description = "Course Skill Mapping"

    course_id = fields.Many2one("cdm.course", required=True, ondelete="cascade")
    skill_id = fields.Many2one("cdm.skill", required=True)
    relevance = fields.Float(default=1.0)


class CdmCourseRequest(models.Model):
    _name = "cdm.course.request"
    _description = "Course Request"
    _inherit = ["mail.thread", "mail.activity.mixin"]

    name = fields.Char(default="New", copy=False)
    employee_id = fields.Many2one("hr.employee", required=True)
    course_id = fields.Many2one("cdm.course", required=True)
    justification = fields.Text(required=True)
    target_skill_ids = fields.Many2many("cdm.skill")
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("submitted", "Submitted"),
            ("manager_review", "Manager Review"),
            ("hr_review", "HR Review"),
            ("approved", "Approved"),
            ("rejected", "Rejected"),
            ("in_progress", "In Progress"),
            ("completed", "Completed"),
            ("request_info", "Need More Info"),
        ],
        default="draft",
        tracking=True,
    )
    manager_id = fields.Many2one(related="employee_id.parent_id", store=True)
    approved_on = fields.Datetime()
    completed_on = fields.Datetime()
    total_cost = fields.Float(related="course_id.cost")
    approver_step_ids = fields.One2many("cdm.course.approval.step", "request_id")

    _sql_constraints = [
        (
            "cdm_unique_active_course_request",
            "unique(employee_id, course_id, state)",
            "Duplicate active request in the same state is not allowed.",
        )
    ]

    @api.model_create_multi
    def create(self, vals_list):
        seq = self.env["ir.sequence"]
        for vals in vals_list:
            if vals.get("name", "New") == "New":
                vals["name"] = seq.next_by_code("cdm.course.request") or "New"
        return super().create(vals_list)

    @api.constrains("justification")
    def _check_justification(self):
        for rec in self:
            if not rec.justification or len(rec.justification.strip()) < 10:
                raise ValidationError("Please provide a justification with at least 10 characters.")

    def _hr_required(self):
        threshold = float(self.env["ir.config_parameter"].sudo().get_param("cdm.course_cost_hr_threshold", default="0") or 0)
        return self.total_cost >= threshold > 0

    def action_submit(self):
        activity_type = self.env.ref("mail.mail_activity_data_todo")
        for rec in self:
            rec.state = "manager_review"
            if rec.employee_id.parent_id.user_id:
                rec.activity_schedule(
                    activity_type_id=activity_type.id,
                    user_id=rec.employee_id.parent_id.user_id.id,
                    note=f"Please review course request {rec.name}",
                )

    def action_manager_approve(self):
        for rec in self:
            if rec._hr_required():
                rec.state = "hr_review"
            else:
                rec.state = "approved"
                rec.approved_on = fields.Datetime.now()

    def action_hr_approve(self):
        for rec in self:
            rec.state = "approved"
            rec.approved_on = fields.Datetime.now()

    def action_reject(self):
        self.write({"state": "rejected"})


class CdmCourseApprovalStep(models.Model):
    _name = "cdm.course.approval.step"
    _description = "Course Approval Step"

    request_id = fields.Many2one("cdm.course.request", required=True, ondelete="cascade")
    step_type = fields.Selection([("manager", "Manager"), ("hr", "HR")], required=True)
    approver_user_id = fields.Many2one("res.users", required=True)
    decision = fields.Selection([("approve", "Approve"), ("reject", "Reject"), ("request_info", "Request Info")])
    decision_on = fields.Datetime()
    comments = fields.Text()
