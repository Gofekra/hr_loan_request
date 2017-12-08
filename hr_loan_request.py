#-*- coding:utf-8 -*-

import time
import logging
from datetime import date
from datetime import datetime
from datetime import timedelta
from dateutil import relativedelta
from dateutil import parser
import calendar
from dateutil.relativedelta import relativedelta

from openerp import netsvc
from openerp.osv import fields, osv
from openerp import tools
from openerp.tools.translate import _
import openerp.addons.decimal_precision as dp

#from openerp.tools.safe_eval import safe_eval as eval

import string
import StringIO
import base64

class hr_loan_request_type(osv.osv):
	_name="hr.loan.request.type"
	_description="Les differents type de pret possible"
	_columns = {
		'code':fields.char('Code', size=64),
		'amount_max':fields.integer('Montant Max'),
		'cession_max':fields.integer('Cession Max (%)'),        
		'age_max':fields.integer('Age Max'),        
		'duree_max':fields.integer('Duree Max (Mois)'),
		'name':fields.char('Type de pret', size=64),
		'rate':fields.float('Taux'),
		'rubrique_id':fields.many2one('hr.payroll_ma.ligne_rubrique','Rubrique'),
        'rubriques_id':fields.many2one('hr.payroll_ma.rubrique','Rubriques'),
        #'ref':fields.char('Reference',size=64),
        'limited_on_current_year':fields.boolean('Limite sur l\'annee en cours'),
        'formule': fields.char('Formule',size=128, help='''
        Pour les calcule de quotite cessible,Capital et/ou Plafond on utilise les variables suivantes :
            salaire_base : Salaire de base
            Transport : Indemnite de Transport
            Logement : Indemnite de Logement
            Anciennete : Prime d anciennete
            constante : Constant (pour ppe en generale)
        '''),
        'formule_plafond': fields.char('Formule Plafond',size=128, help='''
            Pour les calcule de quotite cessible,Capital et/ou Plafond on utilise les variables suivantes :
                salaire_base : Salaire de base
                Transport : Indemnite de Transport
                Logement : Indemnite de Logement
                Anciennete : Prime d anciennete
                constante : Constant (pour ppe en generale)
        '''),
        'rub_code': fields.char('Code de ligne de rubrique',size=64),
        'constante':fields.float('Constante'),
        'rate_ids': fields.one2many('hr.loan.request.type.rate', 'name', 'Les taux'),
        #'rubrique_ids': fields.one2many('hr.payroll_ma.ligne_rubrique', 'id_contract', 'Les rubriques'),
		}
hr_loan_request_type()

###################################

class hr_loan_request(osv.osv):
    _name="hr.loan.request"
    _description="Gestion de demandes de prêts"
    
    STATES = [('draft', 'Brouillon'),
        ('open', 'Ouverte'),
        ('valid1','DAP'),
        ('valid2','DRH'),
        ('valid3','DG'),        
        ('done', 'Terminer'),
        ('decline','Refuser'),
        ('cancel', 'Annuler')]

    FOLDED_STATES = ['done','cancel'] 
    
    def create(self, cr, uid, vals, context=None):
        if vals.get('name','/')=='/':
            vals['name'] = self.pool.get('ir.sequence').get(cr, uid, 'hr.loan.request') or '/'
        return super(hr_loan_request, self).create(cr, uid, vals, context=context)
        
    def _employee_get(self, cr, uid, context=None):
        ids = self.pool.get('hr.employee').search(cr, uid, [('user_id', '=', uid)], context=context)
        if ids:
            return ids[0]
        return False    

    # this is the original version
    # def _get_repayment(self, cr, uid, ids, field_name, arg, context):
    #     # raise osv.except_osv(_('var content'),_('ids = %s \n field_name = %s \n arg = %s')%(ids,field_name,arg))
    #     result={}      
    #     for loan in self.browse(cr,uid,ids):
            
    #         rate=loan.rate
    #         term=loan.term_request
    #         monthly_interest=rate/(100*12)
    #         principal=loan.amount_request
    #         payment_number=term
    #         if rate!=0:
    #             result[loan.id]=principal * ( monthly_interest / (1 - (1 + monthly_interest) ** (- payment_number)))
    #         else:
    #             result[loan.id]=principal/term
    #         result[loan.id]=round(result[loan.id],-3)
    #     return result

    def _get_repayment(self, cr, uid, ids, field_name, arg, context):
        """
            retourne montant de la mensualite
            ids est une liste
            field_name est le champ repayment_request
        """
        # raise osv.except_osv(_('var content'),_('ids = %s \n field_name_type = %s field_name = %s \n arg = %s')%(ids,type(field_name),field_name,arg))
        result={}
        rate = []
        tranche = []
        repayment_by_tranche = [] #mensualite par tranche (la somme donne la mensualite exacte)
        repayment_final = 0
        # K = 12.218441293
        K = 12
        for loan in self.browse(cr,uid,ids):
            principal=loan.amount_request
            type_id = loan.request_type.id
            term=loan.term_request
            # raise osv.except_osv(_('r_type'),_('rt = %s')%(request_type))
            rates = self._get_rate(cr,uid,ids,type_id)
            # raise osv.except_osv(_('rates'),_('rates = %s')%(rates))
            if len(rates)!=0 and len(rates)>1:
                finish = False
                for rt in rates:
                    data={}
                    if not finish:
                        if principal > rt['amount_max']:
                            data['principal'] = rt['amount_max']
                            data['rate'] = rt['rate']
                            principal = principal-rt['amount_max']
                            tranche.append(data)
                        elif principal == rt['amount_max']:
                            data['principal'] = rt['amount_max']
                            data['rate'] = rt['rate']
                            tranche.append(data)
                            finish = True
                        else:
                            data['principal'] = principal
                            data['rate'] = rt['rate']
                            tranche.append(data)
                            finish = True
            elif len(rates)!=0 and len(rates)==1:
                rt = rates[0]
                data={}
                data['principal'] = principal
                data['rate'] = rt['rate']
                tranche.append(data)
            else:
                raise osv.except_osv(_('Error'),_('Veuillez definir un taux pour ce type de pret'))
            # raise osv.except_osv(_('tranche'),_('tranche = %s')%(tranche))
            if len(tranche)!=0:
                for tr in tranche:
                    # repayment_by_tranche = 0
                    data_repayment = {}
                    rate_by_tranche = tr['rate']
                    amount_tranche = tr['principal']

                    monthly_interest = (float(rate_by_tranche)/100/K) #taux interet a  diviser par 12 pour avoir le taux mensuel
                    # raise osv.except_osv(_('monthly_interest'),_('monthly_interest = %s')%(monthly_interest))
                    # ttest = amount_tranche * (rate_by_tranche/100/12.218441293)
                    # raise osv.except_osv(_('ttest'),_('ttest = %s')%(ttest))
            # rate=loan.rate
            # term=loan.term_request
            # monthly_interest=rate/(100*12)
            # payment_number=term
                    payment_number=term
                    if rate_by_tranche!=0:
                        # result[loan.id]=principal * ( monthly_interest / (1 - (1 + monthly_interest) ** (- payment_number)))
                        #test
                        test = (1 + monthly_interest) **(-payment_number)
                        
                        # raise osv.except_osv(_('test'),_('test = %s')%(test))
                        denominateur = 1 - test
                        if denominateur == 0:
                            denominateur = 1
                            raise osv.except_osv(_('warning'),_('La division par zero est impossible'))
                        # raise osv.except_osv(_('test'),_('test = %s \n payment_number = %s')%(test,payment_number))
                        # repayment_request = (amount_tranche * (monthly_interest/12)) / (1-((1 + (monthly_interest/12)) ** (-payment_number)))
                        repayment_request = (amount_tranche * monthly_interest) / denominateur #(1-((1 + monthly_interest) ** (-payment_number)))
                        data_repayment['repayment_request'] = round(repayment_request,2)
                    else:
                        # result[loan.id]=principal/term
                        data_repayment['repayment_request']=round((amount_tranche/payment_number),2)
                    repayment_by_tranche.append(data_repayment)
        # raise osv.except_osv(_('repayment_by_tranche'),_('repayment_by_tranche = %s \n term = %s')%(repayment_by_tranche,term))
        for rpayment in repayment_by_tranche:
            repayment_final += rpayment['repayment_request']
        # result[loan.id]=round(result[loan.id],-3)
        result[loan.id]=round(repayment_final,2)
        # raise osv.except_osv(_('result[loan.id]'),_('result = %s')%(result))
        return result

    def _get_rate(self, cr, uid, ids, type_id, context=None):
        """
            retourne une liste contenant des dictionnaires 
            elle meme contenant les baremes des taux
        """
        result=[]
        loan_type = self.pool.get('hr.loan.request.type').browse(cr, uid, [type_id], context=context)
        for lt in loan_type:
            taux_dict={}
            for rate_id in lt.rate_ids:
                taux_dict={}
                taux_dict['rate'] = rate_id.rate
                taux_dict['amount_min'] = rate_id.amount_min
                taux_dict['amount_max'] = rate_id.amount_max
                result.append(taux_dict)
        #raise osv.except_osv(_('result'),_('result = %s')%result)
        return result

    def compute_mensuality(self, cr,uid, montant, term, rate):
        """
            calcul la mensualite a partir de trois element:
            - montant = la somme demande
            - term = duree de remboursement (en mois)
            - rate = le taux annuel de remboursement
        """
        
        numerateur = 0
        denominateur = 0
        mensuality = 0
        if rate == 0:
            monthly_rate = 0
        else:
            monthly_rate = rate/12/100

        if monthly_rate!=0:
            numerateur = montant * monthly_rate
            denominateur = 1-(1+monthly_rate)**(-term)
            mensuality = float(numerateur)/float(denominateur)
            repayment_request=mensuality
        else:
            mensuality = montant/term
            repayment_request=mensuality
        result=round(repayment_request,-3)
        # raise osv.except_osv(_('values')
        #     , _('montant = %s \n term = %s \n rate = %s \n monthly_rate = %s \n mensuality = %s')%(montant,term,rate,monthly_rate,mensuality))
        return result
            
    def state_groups(self,cr,uid, ids, domain, **kwargs):
        folded = {key: (key in self.FOLDED_STATES) for key, _ in self.STATES}
        return self.STATES[:], folded

    _group_by_full = {
        'state': state_groups
    }

    def _read_group_fill_results(self, cr, uid, domain, groupby,remaining_groupbys, aggregated_fields,
                                count_field, read_group_result,
                                read_group_order=None, context=None):
        """
            The method seems to support grouping using m2o fields only,
            while we want to group by a simple status field.
            Hence the code below - it replaces simple status values
            with (value, name) tuples.
        """
        read_group_order=None
        if groupby == 'state':
            STATES_DICT = dict(self.STATES)
            for result in read_group_result:
                state = result['state']
                result['state'] = (state, STATES_DICT.get(state))
        return super(hr_loan_request, self)._read_group_fill_results(
            cr, uid, domain, groupby, remaining_groupbys, aggregated_fields,
            count_field, read_group_result, read_group_order, context
        )
        
    _columns = {
		'amount_approve':fields.float('Montant validé'),
		'amount_request':fields.float('Montant demandé',help="presente à defaut la quotite cessible maximum"
            ,readonly=True, states={'draft': [('readonly', False)],}),
		'date':fields.date('Date de demande',readonly=True, states={'draft': [('readonly', False)],}),
		'date_end':fields.date('Date Fin',readonly=True, states={'valid3': [('readonly', False)],}),
		'date_start':fields.date('Date debut',readonly=True, states={'valid3': [('readonly', False)],}),
		'employee_id':fields.many2one('hr.employee','Employe (1)',readonly=True, states={'draft': [('readonly', False)],}),
		'motif':fields.char('Motif', size=64,readonly=True, states={'draft': [('readonly', False)],}),
		'name':fields.char('Numero', size=64),
		'note':fields.text('Remarques'),
		'rate':fields.related('request_type','rate',type='float',string='Taux'),
		'repayment':fields.float('Mensualite'),
		'repayment_approve': fields.float('Mensualite',readonly=True, states={'open': [('readonly', False)],}),
		'repayment_request':fields.function(_get_repayment, type='float', string='Mensualité', method=True, store=False),
        #'repayment_request':fields.float('Mensualité'),
        'request_type':fields.many2one('hr.loan.request.type','Type de prêt (2)',required=True,readonly=True, states={'draft': [('readonly', False)],}),
		'rubrique_id':fields.many2one('hr.payroll_ma.ligne_rubrique','Rubrique'),#anciennement ligne_rubrique
        # 'rubriques_id':fields.many2one('hr.payroll_ma.rubrique','Rubriques'),#anciennement ligne_rubrique
		'rubriques_id':fields.related('request_type','rubriques_id',type='many2one',relation='hr.payroll_ma.rubrique',string='Rubriques'),
        # 'advantage_id':fields.many2one('hr.employee.advantage','Avantages')

        'state':fields.selection(
            STATES,
            'Etat',readonly=True),
		'term_approve':fields.integer('Durée validé (Mois)',readonly=True, states={'open': [('readonly', False)],}),
		'term_request':fields.integer('Durée demandé (Mois)',readonly=True, states={'draft': [('readonly', False)],}),
        'term_max':fields.integer('Durée max autorise (Mois)',readonly=True, states={'draft': [('readonly', True)],}),
		'repayment_first':fields.float('First repayment'),
		'repayment_from_sqlserver':fields.float('sql server repayment'), #just for comparaison for result generated by openerp
		'request_number':fields.integer('request number'),
        'amount_max': fields.float('Plafond',readonly=True),
        'amount_max_test': fields.float('Plafond test'),
        # 'repayment_request':fields.function(_get_repayment, type='float', string='Mensualité', method=True, store=False),
        'repayment_max': fields.float('Quotité cessible',readonly=True),

		}
		
    _defaults = {
        'term_request': 1,
        'date': fields.date.context_today,
        'state': 'draft',
        'employee_id':_employee_get,
        'name': lambda obj, cr, uid, context: '/',
        'amount_max':0
		}
    
    def generate_payroll_line(self,cr,uid,ids,context=None):
        """
            techniquement, le boutton faisant appel a cette
            methode ne devrait apparaitre que si:
            state is in ('valid1','valid2','valid3')
            donc, pas la peine de mettre une condition sur state
        """
        employee_id = 0
        id_contract = 0
        rubriques_id = 0
        date_start = 0
        date_stop = 0
        montant = 0
        permanent = False

        self_loan = self.browse(cr,uid,ids)
        payroll_line_obj = self.pool.get('hr.payroll_ma.ligne_rubrique')
        
        employee_id = self_loan.employee_id.id
        id_contract = self._get_employee_contract(cr,uid,ids,employee_id)[0]
        rubriques_id = self_loan.rubriques_id.id
        date_start = self_loan.date_start
        date_stop = self_loan.date_end
        montant = self_loan.repayment_approve

        # period_id = datetime
        month = int(date_stop.split('-')[1])
        year = str(date_stop.split('-')[0])
        code_periode  = 0
        if month < 10:
            code_periode = '0'+str(month)+'/'+year
        else:
            code_periode = str(month)+'/'+year
        period_obj = self.pool.get('account.period')
        pr_id = period_obj.search(cr,uid,[('code','like',code_periode)])
        pr_id = period_obj.browse(cr,uid,pr_id)

        critere = [ ('employee_id','=',employee_id),
                    ('id_contract','=',id_contract),
                    ('rubrique_id','=',rubriques_id),
                    ('date_start','=',date_start),
                    ('date_stop','=',date_stop,),
                    ('montant','=',montant),
                    ('permanent','=',permanent)
                ]
        pay_id = payroll_line_obj.search(cr,uid,critere)

        l={
            'employee_id':employee_id,
            'id_contract':id_contract,
            'rubrique_id':rubriques_id,
            'date_start':date_start,
            'date_stop':date_stop,
            'montant':montant,
            'permanent':permanent
        }
        if pay_id!=[]:
            res = payroll_line_obj.write(cr,uid,pay_id,l)
        else:
            res = payroll_line_obj.create(cr,uid,l)
        # raise osv.except_osv(_('loan'),_('rubriques_id = %s')
        #     %(rubriques_id))
        return True

    def done(self,cr,uid,ids,context=None):
        self.generate_payroll_line(cr,uid,ids)
        return True

    def decline(self,cr,uid,ids,context=None):
        # il faut tester si uid est bien un DAP ou autre
        data={}
        data['state']='decline'
        self.write(cr,uid,loan.id,data)
        return True

    def open(self, cr, uid, ids,context=None):
        period_obj = self.pool.get('account.period')
        data={}
        for loan in self.browse(cr,uid,ids):
            data['repayment_approve']=loan.repayment_request
            data['term_approve']=loan.term_request
            data['amount_approve']=loan.amount_request
            data['state']='open'
            data['date_start']=loan.date
            date_end = datetime.strptime(loan.date,'%Y-%m-%d').date()
            month = date_end.month
            year = date_end.year
            day = date_end.day
            month_p = ''
            if month < 10:
                month_p = '0'+str(month)
            
            if loan.term_request == 1:
                code_period = str(month_p)+'/'+str(year)
                period_id = period_obj.search(cr,uid,[('code','=',code_period)])
                period_id = period_obj.browse(cr,uid,period_id)
                if period_id:
                    date_end = period_id.date_stop
                    date_end = datetime.strptime(date_end,'%Y-%m-%d').date()
                # raise osv.except_osv(_('date_end'),_('code_period = %s \n date_end = %s \n period_id = %s \n type = %s')%(code_period,date_end,period_id,type(date_end)))
            else:
                month_sum = loan.term_request #month + 
                mois = 0
                if month_sum >= 12:
                    nb_annee = int(month_sum/12)
                    mois = month_sum%12
                    year += nb_annee
                    # month = mois 
                    month += mois
                    if month > 12:
                        an = int(month/12)
                        year += an
                        month = month%12
                else:
                    mois = month + month_sum
                    if mois > 12:
                        ans = mois/12
                        year += ans
                        month = mois%12
                    else:
                        month = mois

                # date_end = str(year)+'-'+str(month)+'-'+str(day)
                last_date_of_month = datetime(year,month,1)+relativedelta(months=1,days=-1)
                date_end = last_date_of_month.date()
                # raise osv.except_osv(_('date_end'),_('date_end = %s type = %s')%(date_end,type(date_end)))
            data['date_end'] = date_end
            # raise osv.except_osv(_('date_end'),_('date_end = %s \n month = %s \n year = %s \n loan.term_request = %s')
            #     %(loan.date,month,year,loan.term_request))
            self.write(cr,uid,loan.id,data)
        return True

    def validate_dap(self,cr,uid,ids,context=None):
        # il faut tester si uid est bien un DAP ou autre
        data={}
        for loan in self.browse(cr,uid,ids):
            if loan.state == 'open':
                data['state']='valid1'
        if data!=[]:
            self.write(cr,uid,loan.id,data)
        return True
    #test function Hari
    def _get_period_id_now(self, cr, uid):
        """retourne l'id de la periode actuelle"""
        result=[]
        date_now = datetime.today().strftime('%Y-%m-%d')
        date_nows = datetime.strptime(date_now,'%Y-%m-%d').date()
        period = self.pool.get('account.period')
        month = '0'
        if date_nows.month < 10 :
            month = '0'+ str(date_nows.month)
        period_now = month+'/'+str(date_nows.year)
        #raise osv.except_osv(_('Error'), _('period_now = %s')%(period_now))
        period_now = period.search(cr,uid,[('name','=',period_now)])
        if len(period_now)==0:
            raise osv.except_osv(_('Error'), _('Cette periode n\'existe pas! \n Veuillez la creer !'))
        result.append(period_now[0])
        return result

    def compute_employee_loan(self,cr,uid,ids):
        """
            Totalise la somme des dettes de l'employee
            dont le type est: ['PPE','PH','AVEX']
            Cette methode s'utilise uniquement apres la
            methode <_get_employee_loan> car ids est une
            liste d'id (des dettes) qu'il retourne.
        """
        result=[]
        repayment_approve = 0
        obj_loan_browse = self.browse(cr,uid,ids)
        for olb in obj_loan_browse:
            repayment_approve += olb.repayment_approve
        result.append(repayment_approve)
        return result

    def _get_employee_loan(self, cr, uid, ids, employee_id, context=None):
        """retourne l'id des dettes en cours de l'employee"""
        loan_found=['PPE','PH','AVEX']
        print "all employee loan validate"
        date_now = datetime.today().strftime('%Y-%m-%d')
        date_nows = datetime.strptime(date_now,'%Y-%m-%d').date()
        period = self.pool.get('account.period')
        month = '0'
        if date_nows.month < 10 :
            month = '0'+ str(date_nows.month)
        period_now = month+'/'+str(date_nows.year)
        #raise osv.except_osv(_('Error'), _('period_now = %s')%(period_now))
        period_now = period.search(cr,uid,[('name','=',period_now)])
        #raise osv.except_osv(_('Error'), _('period_now = %s')%(period_now))
        res = period.read(cr, uid, period_now , ['date_start'])
        #raise osv.except_osv(_('Error'), _('res = %s')%(res))
        date_start_pn = res[0]['date_start']
        date_start_pn = datetime.strptime(date_start_pn,'%Y-%m-%d').date()
        #raise osv.except_osv(_('Error'), _('date_start_pn = %s')%(date_start_pn))

        result=[]
        
        #raise osv.except_osv(_('Error'), _('date_now = %s')%(date_now))
        al_ids = self.search(cr, uid, [('employee_id','=',employee_id)])
        correct_ids = []
        for l_id in self.browse(cr, uid, al_ids):
            #raise osv.except_osv(_('state'),_('state = %s')%(l_id.state))
            if l_id.request_type.code in loan_found and l_id.state not in ('done','cancel','decline'):
                if l_id.date_end:
                    date_end = datetime.strptime(l_id.date_end,'%Y-%m-%d').date()
                    if date_end > date_start_pn:
                        correct_ids.append(l_id.id)
            
                else:
                    date_ask = str(l_id.date)
                    date_ask = datetime.strptime(date_ask,'%Y-%m-%d').date()
                    #raise osv.except_osv(_('Error'), _('date_ask = %s')%(date_ask))
                    a = l_id.term_request
                    an = int(a/12)
                    mois_a = a%12
                    year_end_loan = date_ask.year + an
                    month_end_loan = date_ask.month + mois_a

                    if month_end_loan > 12:
                        newyear = int(month_end_loan/12)
                        year_end_loan = year_end_loan+newyear
                        month_end_loan = month_end_loan%12
                    #raise osv.except_osv(_('month_end_loan'), _('month_end_loan = %s')%(month_end_loan))

                    date_end_loan_str = str(year_end_loan)+'-'+str(month_end_loan)+'-01' #+str(day_end_loan)
                    date_end_loan = datetime.strptime(date_end_loan_str,'%Y-%m-%d').date()
                    day_end_loan = calendar.mdays[date_end_loan.month]
                    date_end_loan_str = str(year_end_loan)+'-'+str(month_end_loan)+'-'+str(day_end_loan)
                    date_end_loan = datetime.strptime(date_end_loan_str,'%Y-%m-%d').date()
                #raise osv.except_osv(_('dette en cours'), _('date_end_loan = %s et date_start_pn= %s')%(type(date_end_loan),type(date_start_pn)))
                
                    if date_end_loan > date_start_pn:
                        #raise osv.except_osv(_('dette en cours'), _('date_end_loan = %s')%(date_end_loan))
                        correct_ids.append(l_id.id)
        result = correct_ids
            # else:
            #     #'dette payer'
            #     raise osv.except_osv(_('dette payer'), _('date_end_loan = %s')%(date_end_loan))
        #raise osv.except_osv(_('result'),_('result = %s')%(result))
        # raise osv.except_osv(_('Error'), _('result = %s')%(result))
        # for al_id in al_ids:
        #     print("accede au champ hr_loan_request")
        # #al = self.browse(cr,uid,ids)
        # raise osv.except_osv(_('Error'), _('al_ids = %s')%(al_ids))
        # for all_loan in self.browse(cr,uid,ids):
        #     result.append(all_loan)
        #     raise osv.except_osv(_('Error'), _('result = %s')%(all_loan))
        return result

    def _get_employee_contract(self, cr, uid, ids, employee_id, context=None):
        """retourne l'id du contract en vigueur"""
        result = []
        obj_contract = self.pool.get('hr.contract')
        obj_period = self.pool.get('account.period')
        period_id = self._get_period_id_now(cr,uid)
        period_id = obj_period.search(cr,uid,[('id','=',period_id[0])])
        period_id_read = obj_period.read(cr,uid,period_id,['date_start']) #retourne une liste de dict
        # raise osv.except_osv(_('Error'), _('period_id_read = %s')%(period_id_read))
        #res = period.read(cr, uid, period_now , ['date_start'])
        date_start = period_id_read[0]['date_start']
        contract_ids = obj_contract.search(cr, uid, [('employee_id','=',employee_id)
                            ,'|',('date_end','in',(False)),('date_end','>',date_start)
                            ,('date_start','<=',date_start)]
                            , order='date_start desc', context=context)
        if len(contract_ids)!=0:
            result.append(contract_ids[0])
        else:
            raise osv.except_osv(_('Error'), 
                _('Ou Le contrat de cette employe est ferme ou il ne possede pas! \n Il faut lui creer un nouveau contrat ou le desactive !'))
        
        return result
    
    #end test function
    def onchange_amount_original(self, cr, uid, ids,amount_request,amount_max,context=None):
        res={}
        # raise osv.except_osv(_('warning'),_('ids = %s')%(ids))
        res['amount_request']=round(min(amount_request,amount_max),2) #-3
        # res['repayment_request']=
        return {'value':res}

    def onchange_amount(self, cr, uid, ids,amount_request,amount_max,term_request,context=None):
        res={}
        # raise osv.except_osv(_('warning'),_('term_request = %s')%(term_request))
        res['amount_request']=round(min(amount_request,amount_max),0) #-3
        # res['term_request'] = term_request + 1
        # res['repayment_request']=
        # self.onchange_type(cr,uid,ids,type_id,employee_id)
        return {'value':res}

    def onchange_term_request(self, cr, uid, ids,term_request,term_max,context=None):
        res={}
        res['term_request']=round(min(term_request,term_max),2) #-3
        return {'value':res}

    def _get_term_limit(self, cr, uid, type_id, employee_id, context=None):
        """
            retourne sous forme de tableau le nombre de mois max qu un employe
            peut avoir pour rembousser sa dette
        """
        obj_loan_type = self.pool.get('hr.loan.request.type')
        obj_employee = self.pool.get('hr.employee')
        employee = obj_employee.browse(cr,uid,[employee_id])
        term = 0
        birthday = employee.birthday
        current_date=datetime.now()
        current_year=current_date.year
        current_month=current_date.month
        if employee.birthday:
            age=parser.parse(employee.birthday) #contient une date
        else:
            raise osv.except_osv(_('warning'),_('renseigner la date de naissance de cette employee'))
        current_age=current_year-age.year

        loan_type = obj_loan_type.browse(cr,uid,[type_id])
        for lt in loan_type:
            term=(lt.age_max-current_age)*12
            if term<=0:
                term=1
            term=min(lt.duree_max,term)
            if lt.limited_on_current_year:
                term = lt.duree_max - current_month

        result = []
        result.append(term)
        return result

    def onchange_type_old(self, cr, uid, ids,type_id,employee_id,context=None):
        if type_id == False:
            return False
        #variable = ['13','31','32']
        lt_code =['AVEX','PH','AV15']
        obj_period = self.pool.get('account.period')
        period_id_now = self._get_period_id_now(cr,uid)
        period_id_read = obj_period.read(cr,uid,period_id_now,['date_start'])
        date_auj = period_id_read[0]['date_start']
        date_auj = datetime.strptime(date_auj,'%Y-%m-%d').date()
        month_auj = date_auj.month
        constante = 1
        lt_plafond = 0
        plafond = 0
        salaire_base = 0
        Anciennete = 0 #13
        Transport = 0 #31
        Logement = 0 #32
        code = 0
        montant_standard = 0
        cession_max = 100
        nb_mois_max = 0
        formule = 0
        Montant_arrieres = 0
        taux = 0
        age_max = 0
        current_date=datetime.now()
        current_year=current_date.year
        

        obj_payroll_line_rub = self.pool.get('hr.payroll_ma.ligne_rubrique')
        obj_contract = self.pool.get('hr.contract')
        contract_id = self._get_employee_contract(cr, uid, ids, employee_id)
        contract_id_read = obj_contract.read(cr,uid,contract_id,['date_start','wage'])
        salaire_base = contract_id_read[0]['wage']
        rubriques=[]
        rubriques_remb = []
        dette_ids = self._get_employee_loan(cr, uid, ids, employee_id)
        result={}
        employee=self.pool.get('hr.employee').browse(cr,uid,[employee_id])[0]
        bulletin_obj=self.pool.get('hr.payroll_ma.bulletin')
        #bulletins=bulletin_obj.search(cr, uid, [('employee_id','=',employee.id),('period_id','=','xxxxxx')]) #,limit=1
        bulletins=bulletin_obj.search(cr, uid, [('employee_id','=',employee.id)],limit=1) #
        bulletins=bulletin_obj.browse(cr,uid,bulletins)
        age=parser.parse(employee.birthday)
        current_age=current_year-age.year     
        loan_type = self.pool.get('hr.loan.request.type').browse(cr, uid, [type_id], context=context)
        if loan_type.id:
            for lt in loan_type:
                code = str(lt.rub_code).split(',')
                lt_plafond = lt.amount_max
                constante = lt.constante
                taux = lt.rate
                result['rate']=lt.rate
                formule = lt.formule
                cession_max = lt.cession_max
                cession_max = float(cession_max)/100
                nb_mois_max = lt.duree_max
                result['rubriques_id']=lt.rubriques_id.id
                term = 0
                limit_emp = 0
                if lt.age_max == 0:
                    raise osv.except_osv(_('Erreur configuration')
                        ,_('la valeur "age_max" dans type de pret n\'est pas defini.\n Mettre une grande valeur pour dire illimite'))
                if nb_mois_max!=0:
                    term=(lt.age_max-current_age)*12
                    limit_emp = term
                    #raise osv.except_osv(_('term'),_('term = %s')%(term))
                if term<=0:
                    term=1
                term=min(lt.duree_max,term)
                # result['term_request']=nb_mois_max
                
                if nb_mois_max not in (1,0):
                    limiter = False
                    if lt.code == lt_code[0]:
                        #AVEX
                        limiter = True
                        nb_mois_max = nb_mois_max - month_auj
                    elif lt.code ==lt_code[1]:
                        #PH
                        limiter = False
                        nb_mois_max = limit_emp
                    else:
                        nb_mois_max = nb_mois_max #elle conserve sa valeur
                    if limiter:
                        nb_mois_max=min(nb_mois_max,term)
                    result['term_request']=nb_mois_max
                elif nb_mois_max == 0:
                    raise osv.except_osv(_('Error'),
                    _('La valeur de duree max n\'est pas defini pour ce type de pret.\n Un emprunt doit toujours avoir une duree de paiment max!'))
                else:
                    nb_mois_max = 1
                if lt.rubriques_id:
                    rubriques_remb.append(lt.rubriques_id.code)
                if lt.rubrique_id:
                    rubriques.append(lt.rubrique_id.code)
        else:
            raise osv.except_osv(_('Attention !'), _('rien par defaut \n Choisir employee avant de choisir le type de pret'))
        for bulletin in bulletins:
            for bulletin_line in bulletin.salary_line_ids:
                if bulletin_line.name[0:2] in code:
                    if bulletin_line.name[0:2] == code[0]:
                        #13 Anciennete
                        Anciennete = bulletin_line.subtotal_employee
                    elif bulletin_line.name[0:2] == code[1]:
                        Transport = bulletin_line.subtotal_employee
                    elif bulletin_line.name[0:2] == code[2]:
                        Logement = bulletin_line.subtotal_employee
        try:
            #rubrique['montant'] = eval(str(rubrique['formule']))
            formule = str(formule)
            plafond = round(eval(formule),-3) #amount_request
            if lt_plafond != 0:
                result['amount_max']=min(plafond,lt_plafond)
            else:
                result['amount_max']=plafond
            result['amount_request']=round(result['amount_max'],-3)
            #raise osv.except_osv(_('Formule Error !'), _('Formule Error : %s ' % (e)))
        except Exception, e:
            raise osv.except_osv(_('Formule Error !'), _('Formule Error : %s ' % (e)))

        current_payments=0
        
        for bulletin in bulletins:
            salaire_net=bulletin.salaire_net
            for bulletin_line in bulletin.salary_line_ids:
                if bulletin_line.name[0:2] in rubriques:
                    current_payments=current_payments.bulletin_line.subtotal_employee
        
        # logger = netsvc.Logger()
        # logger.notifyChannel('ott', netsvc.LOG_INFO, salaire_net)

        result['term_request']=nb_mois_max
        result['repayment_request']=self.compute_mensuality(cr,uid,result['amount_request'],result['term_request'],result['rate'])
        # warning = {
        #     'title': _('Mensualité!'),
        #     'message' : _('Le repaiement mensuel sera de AR '+str(result['repayment_request'])+' . \n')
        #     }
        return {'value': result}

    def _get_rate_anciennete(self, cr, uid, ids):
        """ids doit contenir le ID d'un employee c'est un entier"""
        # raise osv.except_osv(_('ids'),_('ids = %s')%(type(ids)))
        taux=0
        id_employee = ids
        obj_employee = self.pool.get('hr.employee').browse(cr,uid,[ids])
        obj_period = self.pool.get('account.period')
        period_id = self._get_period_id_now(cr,uid)
        period_id_search = obj_period.browse(cr,uid,period_id)
        date_auj = period_id_search.date_start
        date_auj = datetime.strptime(date_auj,'%Y-%m-%d').date()
        if obj_employee.date_bis==False:
            date_embauche = obj_employee.date
        else:
            date_embauche = obj_employee.date_bis
        if obj_employee.anciennete:
            date_auj = str(date_auj).split('-')
            date_embauche = date_embauche.split('-')
            anciennete=int(date_auj[0])-int(date_embauche[0])
            objet_anciennete = self.pool.get('hr.payroll_ma.anciennete')
            id_anciennete = objet_anciennete.search(cr, uid, [])
            liste = objet_anciennete.read(cr, uid, id_anciennete, ['debuttranche', 'fintranche', 'taux'])
            anciennete=int(anciennete)
            #logger.notifyChannel('Anciennete', netsvc.LOG_INFO, anciennete)
            for tranche in liste:
                if(anciennete >= tranche['debuttranche']) and (anciennete < tranche['fintranche']):
                    taux = tranche['taux']
            return taux
        else:
            return 0.0

    # sauvegarde du code source
    def onchange_type(self, cr, uid, ids,type_id,employee_id,context=None):
        if type_id==False:
            return False

        Anciennete_rate = self._get_rate_anciennete(cr,uid,employee_id)
        Anciennete_rate = float(Anciennete_rate)/100
        term_limit = self._get_term_limit(cr,uid,type_id,employee_id)[0]
        # raise osv.except_osv(_('term_limit'),_('term_limit = %s')%(term_limit))
        loan_emp = self._get_employee_loan(cr,uid,ids,employee_id)
        montant_dette = self.compute_employee_loan(cr,uid,loan_emp)[0]
        #raise osv.except_osv(_('montant_dette'),_('montant_dette = %s')%(montant_dette))
        result={}
        result['term_max'] = term_limit

        salaire_base=0
        Anciennete = 0
        Transport = 0
        Logement = 0
        cession_max = 0
        qcess = 0
        nb_mois_max = term_limit
        Montant_arrieres = montant_dette
        constante = 0
        formule = ''
        formule_plafond = ''
        RB = ['13','31','32']
        contract_id = 0
        have_bulletins = True
        rubriques=[]
        rubrique_base = []
        current_payments=0
        employee=self.pool.get('hr.employee').browse(cr,uid,[employee_id])[0]
        obj_contract = self.pool.get('hr.contract')
        bulletin_obj=self.pool.get('hr.payroll_ma.bulletin')
        contract_id = self._get_employee_contract(cr, uid, ids, employee_id)
        bulletins=bulletin_obj.search(cr, uid, [('employee_id','=',employee.id)],limit=1) #return list

        if len(bulletins)!=0:
            bulletins=bulletin_obj.browse(cr,uid,bulletins)
        else:
            have_bulletins = False
        loan_type = self.pool.get('hr.loan.request.type').browse(cr, uid, [type_id], context=context)
        current_date=datetime.now()
        rates = []
        rates = self._get_rate(cr,uid,ids,type_id)
        # raise osv.except_osv(_('taux_d'),_('taux_d = %s')%(taux_d))
        for lt in loan_type:
            constante = float(lt.constante)
            #raise osv.except_osv(_('warning'),_('taux_d = %s')%(taux_d))
            if lt.rub_code:
                rubrique_base=lt.rub_code.split(',')
            if lt.formule:
                formule = str(lt.formule)
            else:
                formule = '0'
            if lt.formule_plafond:
                formule_plafond = str(lt.formule_plafond)
            else:
                formule_plafond = '0'
            cession_max = float(lt.cession_max)/100
            if lt.rubrique_id:
                rubriques.append(lt.rubrique_id.code)
        ##Hari voir formule eval
        contract_id_browse = obj_contract.browse(cr,uid,contract_id,context=context)
        for c_id in contract_id_browse:
            salaire_base = c_id.wage
        # raise osv.except_osv(_('warning'),_('salaire_base = %s')%(salaire_base))
        if have_bulletins:
            for bulletin in bulletins:
                salaire_net=bulletin.salaire_net
                for bulletin_line in bulletin.salary_line_ids:
                    if bulletin_line.name[0:2] in rubriques:
                        current_payments=current_payments.bulletin_line.subtotal_employee

                    if bulletin_line.name[0:2] in rubrique_base:
                        # salaire_base+=bulletin_line.subtotal_employee
                        if bulletin_line.name[0:2] == rubrique_base[0]:
                            Anciennete = bulletin_line.subtotal_employee
                        elif bulletin_line.name[0:2] == rubrique_base[1]:
                            Transport = bulletin_line.subtotal_employee
                        else:
                            Logement = bulletin_line.subtotal_employee
        else:
            contract_id_browse = obj_contract.browse(cr,uid,contract_id,context=context) #retourne nom de l'objet et les infos entre ()
            for c_id in contract_id_browse:
                for rub_id in c_id.rubrique_ids:
                    #rub_id contient le meme resultat qu'un browse: rub_id = hr.payroll_ma.ligne_rubrique(20499,)
                    code_rub_id = rub_id.rubrique_id.code
                    if code_rub_id in rubrique_base:
                        if code_rub_id == RB[0]:
                            Anciennete = salaire_base * Anciennete_rate
                        elif code_rub_id == RB[1]:
                            Transport = rub_id.montant #rub permanent donc une seule fois 
                        else:
                            Logement = rub_id.montant
                    #raise osv.except_osv(_('code_rub_id'),_('rub_id.id = %s \n code_rub_id = %s')%(rub_id.id,code_rub_id))
        qcess = round(eval(formule),2) #-3
        if qcess != 0:
            result['repayment_max']=qcess
        else:
            raise osv.except_osv(_('warning'),_('Aucune formule defini pour la quotite cessible'))
        current_payments = Montant_arrieres
        amount_max = round(eval(formule_plafond),2) #-3
        if amount_max != 0:
            result['amount_max'] = round(amount_max,0)

        else:
            amount_max = (qcess * term_limit/4)-current_payments
            result['amount_max'] = round(amount_max,0)
        
        result['amount_request'] = result['amount_max'] #initialement le montant demande est defini comme le montant max
        result['amount_max_test'] = result['amount_max']
        tranche = []
        K=12
        repayment_by_tranche = []
        for lt in loan_type:
            principal = amount_max
            if len(rates)!=0 and len(rates)>1:
                finish = False
                for rt in rates:
                    data={}
                    if not finish:
                        if principal > rt['amount_max']:
                            data['principal'] = rt['amount_max']
                            data['rate'] = rt['rate']
                            principal = principal-rt['amount_max']
                            tranche.append(data)
                        elif principal == rt['amount_max']:
                            data['principal'] = rt['amount_max']
                            data['rate'] = rt['rate']
                            tranche.append(data)
                            finish = True
                        else:
                            data['principal'] = principal
                            data['rate'] = rt['rate']
                            tranche.append(data)
                            finish = True
            elif len(rates)!=0 and len(rates)==1:
                rt = rates[0]
                data={}
                data['principal'] = round(principal,0)
                data['rate'] = rt['rate']
                tranche.append(data)
            else:
                raise osv.except_osv(_('Error'),_('Veuillez definir un taux pour ce type de pret'))
            # raise osv.except_osv(_('tranche'),_('tranche = %s')%(tranche))
            ###########################################""

            if len(tranche)!=0:
                for tr in tranche:
                    # repayment_by_tranche = 0
                    data_repayment = {}
                    rate_by_tranche = tr['rate']
                    amount_tranche = tr['principal']
                    # raise osv.except_osv(_('warning'),_('tr = %s \n term = %s')%(tr,term_limit))
                    monthly_interest = ((float(rate_by_tranche)/100)/K) #taux interet a  diviser par 12 pour avoir le taux mensuel
                    # raise osv.except_osv(_('warning'),_('rate_by_tranche = %s')%(rate_by_tranche))
                    payment_number=term_limit
                    if rate_by_tranche!=0:
                        # result[loan.id]=principal * ( monthly_interest / (1 - (1 + monthly_interest) ** (- payment_number)))
                        #test
                        test = float((1 + monthly_interest))**(-payment_number)
                        
                        # raise osv.except_osv(_('test'),_('test = %s')%(test))
                        denominateur = 1 - test
                        if denominateur == 0:
                            denominateur = 1
                            raise osv.except_osv(_('warning'),_('La division par zero est impossible'))
                        # raise osv.except_osv(_('test'),_('test = %s \n payment_number = %s')%(test,payment_number))
                        # repayment_request = (amount_tranche * (monthly_interest/12)) / (1-((1 + (monthly_interest/12)) ** (-payment_number)))
                        repayment_request = (amount_tranche * monthly_interest) / denominateur #(1-((1 + monthly_interest) ** (-payment_number)))
                        data_repayment['repayment_request'] = round(repayment_request,2)
                        # raise osv.except_osv(_('warning'),_('repayment_request = %s')%(data_repayment['repayment_request']))
                    else:
                        # result[loan.id]=principal/term
                        data_repayment['repayment_request']=round((amount_tranche/payment_number),2)
                    repayment_by_tranche.append(data_repayment)
        # raise osv.except_osv(_('repayment_by_tranche'),_('repayment_by_tranche = %s \n term = %s')%(repayment_by_tranche,term))
        repayment_final = 0
        for rpayment in repayment_by_tranche:
            repayment_final += rpayment['repayment_request']
        ###############################################
        result['amount_request']=round(result['amount_max'],0) #-3
        result['term_request']=term_limit
        result['repayment_request']=round(repayment_final,2)#-3
        ###############################################
        # raise osv.except_osv(_('warning'),_('result = %s')%(result))
        return {'value': result}
                             
hr_loan_request()

class hr_loan_request_type_rate(osv.osv):
    _name = 'hr.loan.request.type.rate'
    _description = """  
                        Definition des taux des types de pret 
                        car ils sont variable suivant 
                        un montant quelques fois
                    """
    _columns = {
        'name': fields.many2one('hr.loan.request.type','Type de pret'),
        'rate': fields.float('Taux annuel'),
        'amount_min': fields.float('Montant min'),
        'amount_max': fields.float('Montant max'),
    }

    _order = "amount_min"

hr_loan_request_type_rate()

