"""Estação AERIS: missão de inspeção de incêndios, em quatro camadas gráficas."""
import math
import numpy as np

FUNDO = (.025,.043,.067)
PAINEL = (.040,.065,.094)
BORDA = (.14,.22,.28)
TEXTO = (.87,.93,.95)
SUAVE = (.44,.57,.65)
CIANO = (.35,.88,.80)
AMBAR = (1,.73,.32)
VERMELHO = (1,.30,.27)


class GeradorPrimitivas:
    """Carga exata e repetível, vetorizada, sem alterar o RNG global."""
    def __init__(self, seed=42):
        self.seed=seed
        self._chave=None
        self._cache_dados_camadas={}

    def atualizar_elementos_estresse(self,qtd_total,num_camadas,proporcao_transparencia=.5,seed=None):
        if isinstance(qtd_total,(bool,np.bool_)) or not isinstance(qtd_total,(int,np.integer)) or qtd_total<0:
            raise ValueError('A quantidade deve ser um inteiro não negativo.')
        if isinstance(num_camadas,(bool,np.bool_)) or not isinstance(num_camadas,(int,np.integer)) or num_camadas not in (2,4):
            raise ValueError('Use duas ou quatro camadas.')
        if (isinstance(proporcao_transparencia,(bool,np.bool_))
                or not isinstance(proporcao_transparencia,(int,float,np.integer,np.floating))
                or not math.isfinite(proporcao_transparencia) or not 0<=proporcao_transparencia<=1):
            raise ValueError('A transparência deve estar entre zero e um.')
        semente=self.seed if seed is None else seed
        if isinstance(semente,(bool,np.bool_)) or not isinstance(semente,(int,np.integer)) or semente<0:
            raise ValueError('A semente deve ser um inteiro não negativo.')
        chave=(int(qtd_total),num_camadas,float(proporcao_transparencia),semente)
        if chave==self._chave:
            return self._cache_dados_camadas
        rng=np.random.default_rng(semente)
        resultado={}
        paletas=((.20,.51,.43),(.26,.59,.70),(.77,.72,.32),(.84,.42,.24))
        for camada in range(num_camadas):
            n=qtd_total//num_camadas+(camada<qtd_total%num_camadas)
            xy=rng.uniform((-.94,-.67),(.15,.54),(n,2)).astype('f4')
            wh=rng.uniform(.002,.012,(n,2)).astype('f4')
            alpha=np.ones(n,dtype='f4')
            transparentes=rng.permutation(n)[:round(n*proporcao_transparencia)]
            alpha[transparentes]=rng.uniform(.15,.55,len(transparentes))
            vertices=np.empty((n,6,6),dtype='f4')
            cantos=np.array(((0,0),(1,0),(1,1),(0,0),(1,1),(0,1)),dtype='f4')
            vertices[:,:,:2]=xy[:,None,:]+wh[:,None,:]*cantos
            vertices[:,:,2:5]=paletas[camada]
            vertices[:,:,5]=alpha[:,None]
            resultado[camada]=vertices.reshape(-1)
        self._chave=chave
        self._cache_dados_camadas=resultado
        return resultado


class InterfaceAeronautica:
    def __init__(self,prim_batch,font_renderer):
        self.batch=prim_batch
        self.font=font_renderer
        self.gerador=GeradorPrimitivas()
        self.exibir_gaussianas=True
        self.exibir_instrumentos=True
        self.cena=None
        self.quantidade_gaussianas=6000
        self.seed_cena=42

    def _texto(self,texto,x,y,tamanho=.030,cor=TEXTO):
        self.font.desenhar_texto(str(texto),x,y,max(.041,tamanho*1.65),*cor,1)

    def _ret(self,x,y,w,h,cor=PAINEL,alpha=1):
        self.batch.adicionar_retangulo(x,y,w,h,*cor,alpha)

    def _linha(self,x1,y1,x2,y2,cor=BORDA,esp=.002,alpha=1):
        self.batch.adicionar_linha(x1,y1,x2,y2,esp,*cor,alpha)

    def _moldura(self,x,y,w,h,cor=BORDA):
        for a,b in (((x,y),(x+w,y)),((x,y+h),(x+w,y+h)),((x,y),(x,y+h)),((x+w,y),(x+w,y+h))):
            self._linha(*a,*b,cor)

    def _circulo(self,x,y,raio,cor=BORDA,preenchido=False,alpha=1):
        vp=self.batch.ctx.viewport
        aspecto=vp[2]/max(1,vp[3])
        self.batch.adicionar_circulo(x,y,raio/aspecto,raio,40,*cor,alpha,
                                    preenchido=preenchido,espessura=.002)

    def renderizar_gpu(self,indice_camada,num_total_camadas,dados):
        if indice_camada!=0 or not self.exibir_gaussianas:
            return
        if self.cena is None:
            from gaussianas import CenaGaussianas
            self.cena=CenaGaussianas(self.batch.ctx,quantidade=self.quantidade_gaussianas,seed=self.seed_cena)
        _,_,w,h=self.batch.ctx.viewport
        self.cena.renderizar(dados,viewport=(round(.025*w),round(.155*h),round(.565*w),round(.64*h)))

    def desenhar_camada_0_fundo(self,dados,stress_verts=None):
        self._ret(-.97,.59,1.17,.13)
        self._moldura(-.97,-.71,1.17,1.43)
        self._texto('01   VISÃO DA MISSÃO',-.94,.665,.033)
        self._texto('GAUSSIAN SPLATTING  /  3D' if self.exibir_gaussianas else 'ATITUDE  /  HORIZONTE',-.94,.615,.024,CIANO)
        if self.exibir_gaussianas and self.cena is not None:
            self._texto(f'{self.cena.quantidade_visivel:,} SPLATS',-.10,.665,.023,SUAVE)
        if not self.exibir_gaussianas:
            # Mesmo centro de rotação para céu e solo; clipping geométrico do painel.
            x0,y0,x1,y1=-.95,-.69,.18,.59
            roll=math.radians(-dados.get('roll',0))
            pitch=dados.get('pitch',0)*.018
            c,s=math.cos(roll),math.sin(roll)
            def recortar(poly):
                for axis,bound,greater in ((0,x0,True),(0,x1,False),(1,y0,True),(1,y1,False)):
                    saida=[]
                    if not poly:
                        break
                    anterior=poly[-1]
                    dentro_a=anterior[axis]>=bound if greater else anterior[axis]<=bound
                    for atual in poly:
                        dentro=atual[axis]>=bound if greater else atual[axis]<=bound
                        if dentro!=dentro_a:
                            t=(bound-anterior[axis])/(atual[axis]-anterior[axis])
                            saida.append(tuple(anterior[k]+t*(atual[k]-anterior[k]) for k in (0,1)))
                        if dentro:
                            saida.append(atual)
                        anterior,dentro_a=atual,dentro
                    poly=saida
                return poly
            for lo,hi,cor in ((0,3,(.10,.26,.39)),(-3,0,(.24,.19,.12))):
                poly=recortar([(-.385+x*c-(y+pitch)*s,-.05+x*s+(y+pitch)*c)
                               for x,y in ((-3,lo),(3,lo),(3,hi),(-3,hi))])
                arr=[[*p,*cor,1] for i in range(1,len(poly)-1) for p in (poly[0],poly[i],poly[i+1])]
                if arr:
                    self.batch.adicionar_triangulos_numpy(np.asarray(arr,dtype='f4').reshape(-1))
        self._ret(-.95,-.69,1.13,.10,FUNDO,.86)
        self._texto('SERRA DO MAR  /  SETOR BR-07',-.92,-.64,.026,SUAVE)
        self._texto('SINTÉTICO',-.02,-.64,.024,AMBAR)
        if stress_verts is not None:
            self.batch.adicionar_triangulos_numpy(stress_verts)

    def desenhar_camada_1_navegacao(self,dados,stress_verts=None):
        self._ret(.23,-.04,.74,.76)
        self._moldura(.23,-.04,.74,.76)
        self._texto('02   NAVEGAÇÃO',.26,.665,.033)
        self._texto('TRÁFEGO / ROTA DE INSPEÇÃO',.26,.615,.023,SUAVE)
        cx,cy=.60,.285
        for x in np.linspace(.26,.94,9):
            self._linha(float(x),.04,float(x),.56,(.065,.11,.14),.001)
        for y in np.linspace(.04,.56,7):
            self._linha(.26,float(y),.94,float(y),(.065,.11,.14),.001)
        self._circulo(cx,cy,.245)
        self._circulo(cx,cy,.122,(.10,.20,.24))
        self._texto('N',cx-.006,.555,.026,CIANO)
        self._texto('10 NM',.78,.065,.021,SUAVE)
        rota=((.36,.10),(.44,.18),(.60,.285),(.72,.40),(.82,.49))
        for a,b in zip(rota,rota[1:]):
            self._linha(*a,*b,CIANO,.003)
        for x,y in rota:
            self._circulo(x,y,.010,CIANO,True)
        self._texto('BR-07',.81,.52,.023,CIANO)
        for alvo in dados.get('tcas_alvos',[]):
            x=cx+alvo['x']*.29
            y=cy+alvo['y']*.30
            cor=AMBAR if alvo.get('alerta') else SUAVE
            for a,b in (((x,y+.013),(x+.010,y)),((x+.010,y),(x,y-.013)),
                        ((x,y-.013),(x-.010,y)),((x-.010,y),(x,y+.013))):
                self._linha(*a,*b,cor,.002)
            self._texto(alvo['rel_alt'],x+.015,y,.021,cor)
        self._linha(cx,cy-.028,cx,cy+.028,TEXTO,.004)
        self._linha(cx-.026,cy-.009,cx,cy+.020,TEXTO,.004)
        self._linha(cx+.026,cy-.009,cx,cy+.020,TEXTO,.004)
        self._texto(f"PROA {dados.get('rumo',0):03.0f}°",.27,.005,.026,CIANO)
        self._texto(f"WPT {dados.get('distancia_waypoint',0):.1f} NM",.66,.005,.026,SUAVE)
        if stress_verts is not None:
            self.batch.adicionar_triangulos_numpy(stress_verts)

    def desenhar_camada_2_pfd(self,dados,stress_verts=None):
        if self.exibir_instrumentos:
            cx,cy=-.385,-.02
            pitch=dados.get('pitch',0)
            roll=math.radians(-dados.get('roll',0))
            for deg in (-15,-10,-5,5,10,15):
                y=(deg-pitch)*.017
                if abs(y)>.30:
                    continue
                width=.13 if deg%10==0 else .075
                c,s=math.cos(roll),math.sin(roll)
                self._linha(cx-width*c-y*s,cy-width*s+y*c,cx+width*c-y*s,cy+width*s+y*c,TEXTO,.002,.65)
                if deg%10==0:
                    self._texto(str(abs(deg)),cx+width+.018,cy+y,.022,TEXTO)
            for sign in (-1,1):
                self._linha(cx+sign*.13,cy,cx+sign*.045,cy,AMBAR,.007)
                self._linha(cx+sign*.045,cy,cx+sign*.045,cy-.025,AMBAR,.005)
            self._circulo(cx,cy,.009,AMBAR,True)
            for x,label,value,unit in ((-.92,'VELOCIDADE',dados.get('velocidade',0),'KTS'),
                                       (-.02,'ALTITUDE',dados.get('altitude',0),'FT')):
                self._ret(x,-.12,.17,.30,FUNDO,.88)
                self._texto(label,x+.012,.145,.020,SUAVE)
                self._texto(f'{value:.0f}',x+.014,.055,.057,TEXTO)
                self._texto(unit,x+.014,-.008,.023,CIANO)
                self._linha(x+.013,-.055,x+.155,-.055,CIANO,.002)
                for n in range(4):
                    self._linha(x+.126,.20+n*.055,x+.153,.20+n*.055,TEXTO,.002,.6)
                    self._linha(x+.126,-.19-n*.055,x+.153,-.19-n*.055,TEXTO,.002,.6)
            self._ret(-.62,.43,.47,.07,FUNDO,.83)
            self._texto(f"HDG  {dados.get('rumo',0):03.0f}°    VS {dados.get('vertical_speed',0):+.0f}",-.60,.463,.029,CIANO)
            self._texto('ALVO / FOCO TÉRMICO',-.56,-.43,.024,AMBAR)
            self._linha(-.41,-.27,-.41,-.34,AMBAR,.002)
            self._linha(-.45,-.31,-.37,-.31,AMBAR,.002)
        if stress_verts is not None:
            self.batch.adicionar_triangulos_numpy(stress_verts)

    def desenhar_camada_3_alertas_eicas(self,dados,stress_verts=None):
        self._ret(.23,-.71,.74,.63)
        self._moldura(.23,-.71,.74,.63)
        self._texto('03   SISTEMAS & EVENTOS',.26,-.135,.031)
        self._linha(.26,-.19,.94,-.19)
        for i,(label,valor,unit,frac,cor) in enumerate((
                ('POTÊNCIA',dados.get('n1_rpm',0),'%',dados.get('n1_rpm',0)/100,CIANO),
                ('COMBUSTÍVEL',dados.get('combustivel',0),'KG',dados.get('combustivel',0)/4500,CIANO),
                ('TEMP. ÓLEO',dados.get('temperatura_oleo',0),'°C',dados.get('temperatura_oleo',0)/100,AMBAR))):
            y=-.25-i*.106
            self._texto(label,.27,y,.025,SUAVE)
            self._texto(f'{valor:.0f} {unit}',.77,y,.029,TEXTO)
            self._ret(.27,y-.039,.66,.010,(.10,.16,.20))
            self._ret(.27,y-.039,.66*min(1,max(0,frac)),.010,cor)
        nivel=dados.get('nivel_alerta',0)
        cor=VERMELHO if nivel>=2 else AMBAR if nivel else CIANO
        self._ret(.26,-.67,.68,.11,cor,.09)
        self._ret(.26,-.67,.004,.11,cor)
        self._texto('ATENÇÃO' if nivel else 'OPERAÇÃO NOMINAL',.28,-.588,.024,cor)
        mensagens=dados.get('mensagens_alerta',[])
        mensagem=mensagens[0] if mensagens else 'Telemetria e enlace disponíveis'
        self._texto(mensagem[:43],.28,-.635,.021,SUAVE)
        if stress_verts is not None:
            self.batch.adicionar_triangulos_numpy(stress_verts)

    def renderizar_camada(self,indice_camada,num_total_camadas,dados,stress_dict):
        metodos=(self.desenhar_camada_0_fundo,self.desenhar_camada_1_navegacao,
                 self.desenhar_camada_2_pfd,self.desenhar_camada_3_alertas_eicas)
        grupos=((0,1),(2,3)) if num_total_camadas==2 else ((0,),(1,),(2,),(3,))
        for logica in grupos[indice_camada]:
            metodos[logica](dados)
        stress=(stress_dict or {}).get(indice_camada)
        if stress is not None and len(stress):
            self.batch.adicionar_triangulos_numpy(stress)

    def release(self):
        if self.cena is not None:
            self.cena.release()
            self.cena=None
