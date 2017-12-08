#-*- coding:utf-8 -*-

from openerp.report import report_sxw
import time
from openerp.osv import fields, osv
from openerp.tools.translate import _

class request(report_sxw.rml_parse):
    def __init__(self, cr, uid, name, context=None):
        super(request, self).__init__(cr, uid, name, context=context)
        self.localcontext.update({
            'time': time,
            'getRepayment' : self.get_repayment,

        })
 
    def arrondi(self,amount):
        res = 0.00
        initial = int(amount*1000)
        copie = int(amount*100)*10
        reste = initial - copie
        
        if reste >= 5:
            res = float((int(amount*100)+1))/100
        else:
            res = float(int(amount*100))/100
        # raise osv.except_osv(_('reste'),_('reste = %s \n amount = %s \n res = %s')%(reste,amount,res))  
        return res


    def get_repayment(self,object_id):
        #object_id=int(object_id)
    	loan_request_obj=self.pool.get('hr.loan.request')
        loan_request=loan_request_obj.browse(self.cr, self.uid,object_id)
        fs = []
        tranche = []
        K=12
        repayment_by_tranche = []
        amortissement = []
        for loan in loan_request:
            count=1
            data=[]
            term=loan.term_approve
            monthly = loan.repayment_approve #mensualite principale
            # monthly_interest=loan.rate/1200
            principal = loan.amount_approve
            # raise osv.except_osv(_('principal'),_('principal = %s')%(principal))
            type_id = loan.request_type.id
            rates=loan_request_obj._get_rate(self.cr, self.uid,object_id,type_id)
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
            
            ###########################################""
            # raise osv.except_osv(_('tranche'),_('tranche = %s')%(tranche))
            if len(tranche)!=0:
                for tr in tranche:
                    # raise osv.except_osv(_('tr'),_('tr = %s')%(tr))
                    # repayment_by_tranche = 0
                    data_repayment = {}
                    rate_by_tranche = tr['rate'] #taux annuel
                    amount_tranche = tr['principal'] #capital et #term = duree

                    monthly_interest = (float(rate_by_tranche)/100/K) #taux interet a  diviser par 12 pour avoir le taux mensuel
                    payment_number=term
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
                        data_repayment['repayment_request'] = repayment_request #round(repayment_request,2)
                        
                    else:
                        # result[loan.id]=principal/term
                        data_repayment['repayment_request']=amount_tranche/payment_number #round((amount_tranche/payment_number),2)
                        # raise osv.except_osv(_('repayment_request'),_('repayment_request = %s')%(data_repayment['repayment_request']))
                    
                    repayment_by_tranche.append(data_repayment)
                    # raise osv.except_osv(_('repayment_by_tranche'),_('repayment_by_tranche = %s')%(repayment_by_tranche))
                    #calcul amortissement par tranche
                    amortissement_par_mois = {}
                    # monthly_tranche = repayment_by_tranche[0]['repayment_request'] #mensualite tranche
                    monthly_tranche = self.arrondi(data_repayment['repayment_request'])
                    # raise osv.except_osv(_('mensualite'),_('mens = %s \n mens_c = %s')
                    #     %(monthly_tranche,data_repayment['repayment_request']))
                    term_inverse = 0
                    initial = True
                    amortissement_par_tranche = []
                    # standard_monthly = monthly_tranche
                    montant_restant = 0
                    buff_term = term
                    if term > 1:
                        while buff_term > 1:
                            amortissement_par_mois = {}
                            buff_term-=1
                            term_inverse +=1
                            amortissement_par_mois['mois']=term_inverse
                            amortissement_par_mois['mensualite']=self.arrondi(monthly_tranche)
                            if initial:
                                initial=False
                                # amortissement_par_mois['interet']=round((amount_tranche*monthly_interest),2)
                                # amortissement_par_mois['principal']=round((monthly_tranche-amortissement_par_mois['interet']),2)
                                # montant_restant = amount_tranche - amortissement_par_mois['principal']
                                # montant_restant = round(montant_restant,2)
                                # amortissement_par_mois['due']=montant_restant
                                amortissement_par_mois['interet']=self.arrondi(amount_tranche*monthly_interest)
                                amortissement_par_mois['principal']=self.arrondi(monthly_tranche-amortissement_par_mois['interet'])
                                montant_restant = self.arrondi(amount_tranche - amortissement_par_mois['principal'])
                                montant_restant = self.arrondi(montant_restant)
                                if montant_restant < 0.9:
                                    amortissement_par_mois['due']=0
                                else:
                                    amortissement_par_mois['due']=self.arrondi(montant_restant)
                            else:
                                print 'blabla'
                                # amortissement_par_mois['interet']=round((montant_restant*monthly_interest),2)
                                # amortissement_par_mois['principal']=round((monthly_tranche-amortissement_par_mois['interet']),2)
                                # montant_restant = montant_restant - amortissement_par_mois['principal']
                                # montant_restant = round(montant_restant,2)
                                # amortissement_par_mois['due']=montant_restant
                                amortissement_par_mois['interet']=self.arrondi(montant_restant*monthly_interest)
                                amortissement_par_mois['principal']=self.arrondi(monthly_tranche-amortissement_par_mois['interet'])
                                montant_restant = montant_restant - amortissement_par_mois['principal']
                                # montant_restant = self.arrondi(montant_restant)
                                if montant_restant < 0.9:
                                    amortissement_par_mois['due']=0
                                else:
                                    amortissement_par_mois['due']=self.arrondi(montant_restant)

                            amortissement_par_tranche.append(amortissement_par_mois)

                        amortissement.append(amortissement_par_tranche)
                    else:
                        raise osv.except_osv(_('warning'),_('aucune amortissement possible'))
                # raise osv.except_osv(_('amortissement'),_('amortissement = %s')%(amortissement))
                longueur=0
                lg = 0
                assemble = []
                if len(amortissement)!=0:
                    longueur=len(amortissement)
                    lg=longueur
                    lga=0
                for amo in amortissement:
                    for dict_amo in amo:
                        assemble.append(dict_amo)
                
                fusion = []
                for asmb in assemble:
                    t=False
                    data = {}
                    data['mois']=asmb['mois']
                    data['mensualite'] = asmb['mensualite']
                    for asmb_a in assemble:
                        if data['mois']==asmb_a['mois']: 
                            if data['mensualite'] != asmb_a['mensualite']:
                                t=True
                                data['mensualite']=self.arrondi(asmb['mensualite']+asmb_a['mensualite'])
                                data['due']=self.arrondi(asmb['due']+asmb_a['due'])
                                data['interet']=self.arrondi(asmb['interet']+asmb_a['interet'])
                                data['principal']=self.arrondi(asmb['principal']+asmb_a['principal'])
                    if t:
                        fusion.append(data)

                tr = term
                tra=0
                
                while tr > 0:
                    fs.append(fusion[tra])
                    tra+=1
                    tr-=1


        datasys = []
        for fus in fs:
            values={}
            values['count']=fus['mois']
            values['monthly']=fus['mensualite'] #monthly
            values['monthly_interest']=fus['interet'] #round(balance*monthly_interest,2)
            values['monthly_principal']=fus['principal']# monthly-values['monthly_interest']
            # balance=round(balance-values['monthly_principal'],2)
            values['balance']=fus['due'] #balance
                # raise osv.except_osv(_('fs'),_('fs = %s')%(fs))
            datasys.append(values)            
        return datasys


        













            # raise osv.except_osv(_('type_id'),_('type_id = %s \n object_id = %s \n rates = %s')
            #     %(type_id,object_id,rates))
            # amount=loan.amount_request
            # monthly=loan.repayment_request
            # fixed_principal_monthly=amount/term
            # balance=amount
            # while count<=term:
            #     values={}
            #     values['count']=count
            #     values['monthly']=monthly
            #     values['monthly_interest']=round(balance*monthly_interest,2)
            #     values['monthly_principal']=monthly-values['monthly_interest']
            #     balance=round(balance-values['monthly_principal'],2)
            #     values['balance']=balance
            #     if balance < 0:
            #         values['balance']=0
            #         #values['monthly_interest']+=balance
            #     data.append(values)
            #     count+=1 
            # return data

report_sxw.report_sxw('report.hr_loan_request.echeance', 
		      	'hr.loan.request', 
			'addons/hr_loan_request/report/echeance.rml', 
			parser=request, 
			header="external")

