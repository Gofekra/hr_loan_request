{
    'name': 'Human Ressources Prêt',
    'version': '1.0',
    'category': 'Human Ressources',
    'description': """Gestion Prêt des Ressources Humaines""",
    'author': 'OpenMind Ltd',
    'website': 'www.omerp.net',
    'license': 'AGPL-3',
    "depends" : ['hr','l10n_mg_hr_payroll'],
    "data" : ['hr_loan_request.xml',
    'hr_loan_request.xml',
    'security/security.xml',
    'security/ir.model.access.csv',
    'security/ir_rule.xml',
],
    "active": False,
    "installable": True
}
