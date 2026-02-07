{
    "name": "Career Development Hub",
    "summary": "Skills, assessments, courses, and team readiness hub",
    "version": "18.0.1.0.0",
    "category": "Human Resources",
    "author": "Career Development Hub",
    "license": "LGPL-3",
    "depends": ["base", "mail", "hr", "survey", "website_slides"],
    "data": [
        "security/cdm_security.xml",
        "security/ir.model.access.csv",
        "data/ir_sequence_data.xml",
        "data/ir_cron_data.xml",
        "views/cdm_core_views.xml",
        "views/cdm_skill_views.xml",
        "views/cdm_employee_views.xml",
        "views/cdm_assessment_views.xml",
        "views/cdm_course_views.xml",
        "views/cdm_menu_views.xml"
    ],
    "application": True,
    "installable": True,
}
