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
VERDE = (.25,.88,.45)

# Constantes semânticas de layout (coordenadas NDC)
# Camada 0: Visão da Missão / Terreno 3D / Horizonte
L0_PAINEL_X = -.97
L0_PAINEL_Y = -.71
L0_PAINEL_W = 1.17
L0_PAINEL_H = 1.43
L0_CABECALHO_H = .13
L0_RODAPE_H = .10
L0_RODAPE_OFFSET_X = .02
L0_RODAPE_OFFSET_Y = .02
L0_CLIP_HORIZONTE = (-.95, -.69, .18, .59)

# Camada 1: Navegação e Tráfego (Radar)
L1_PAINEL_X = .23
L1_PAINEL_Y = -.04
L1_PAINEL_W = .74
L1_PAINEL_H = .76
L1_RADAR_CX = .60
L1_RADAR_CY = .285
L1_RADAR_RAIO_EXTERNO = .245
L1_RADAR_RAIO_INTERNO = .122
L1_TCAS_ESCALA_X = .29
L1_TCAS_ESCALA_Y = .30

# Camada 3: Sistemas & Eventos (EICAS)
L3_PAINEL_X = .23
L3_PAINEL_Y = -.71
L3_PAINEL_W = .74
L3_PAINEL_H = .63
L3_BARRA_X = .27
L3_BARRA_W = .66
L3_BARRA_H = .010
L3_ALERTA_X = .26
L3_ALERTA_Y = -.67
L3_ALERTA_W = .68
L3_ALERTA_H = .11


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
        self._ret(L0_PAINEL_X, L0_PAINEL_Y + L0_PAINEL_H - L0_CABECALHO_H, L0_PAINEL_W, L0_CABECALHO_H)
        self._moldura(L0_PAINEL_X, L0_PAINEL_Y, L0_PAINEL_W, L0_PAINEL_H)
        self._texto('01   VISÃO DA MISSÃO',-.94,.665,.033)
        self._texto('GAUSSIAN SPLATTING  /  3D' if self.exibir_gaussianas else 'ATITUDE  /  HORIZONTE',-.94,.615,.024,CIANO)
        if self.exibir_gaussianas and self.cena is not None:
            self._texto(f'{self.cena.quantidade_visivel:,} SPLATS',-.10,.665,.023,SUAVE)
        if not self.exibir_gaussianas:
            # Mesmo centro de rotação para céu e solo; clipping geométrico do painel.
            x0, y0, x1, y1 = L0_CLIP_HORIZONTE
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
        self._ret(L0_PAINEL_X + L0_RODAPE_OFFSET_X, L0_PAINEL_Y + L0_RODAPE_OFFSET_Y, L0_PAINEL_W - 2*L0_RODAPE_OFFSET_X, L0_RODAPE_H, FUNDO, .86)
        self._texto('SERRA DO MAR  /  SETOR BR-07',-.92,-.64,.026,SUAVE)
        self._texto('SINTÉTICO',-.02,-.64,.024,AMBAR)
        if stress_verts is not None:
            self.batch.adicionar_triangulos_numpy(stress_verts)

    def desenhar_camada_1_navegacao(self,dados,stress_verts=None):
        self._ret(L1_PAINEL_X, L1_PAINEL_Y, L1_PAINEL_W, L1_PAINEL_H)
        self._moldura(L1_PAINEL_X, L1_PAINEL_Y, L1_PAINEL_W, L1_PAINEL_H)
        self._texto('02   NAVEGAÇÃO',.26,.665,.033)
        self._texto('TRÁFEGO / ROTA DE INSPEÇÃO',.26,.615,.023,SUAVE)
        cx, cy = L1_RADAR_CX, L1_RADAR_CY
        for x in np.linspace(.26,.94,9):
            self._linha(float(x),.04,float(x),.56,(.065,.11,.14),.001)
        for y in np.linspace(.04,.56,7):
            self._linha(.26,float(y),.94,float(y),(.065,.11,.14),.001)
        self._circulo(cx, cy, L1_RADAR_RAIO_EXTERNO)
        self._circulo(cx, cy, L1_RADAR_RAIO_INTERNO, (.10,.20,.24))
        self._texto('N',cx-.006,.555,.026,CIANO)
        self._texto('10 NM',.78,.065,.021,SUAVE)
        rota=((.36,.10),(.44,.18),(.60,.285),(.72,.40),(.82,.49))
        for a,b in zip(rota,rota[1:]):
            self._linha(*a,*b,CIANO,.003)
        for x,y in rota:
            self._circulo(x,y,.010,CIANO,True)
        self._texto('BR-07',.81,.52,.023,CIANO)
        for alvo in dados.get('tcas_alvos',[]):
            x = cx + alvo['x'] * L1_TCAS_ESCALA_X
            y = cy + alvo['y'] * L1_TCAS_ESCALA_Y
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
        self._ret(L3_PAINEL_X, L3_PAINEL_Y, L3_PAINEL_W, L3_PAINEL_H)
        self._moldura(L3_PAINEL_X, L3_PAINEL_Y, L3_PAINEL_W, L3_PAINEL_H)
        self._texto('03   SISTEMAS & EVENTOS',.26,-.135,.031)
        self._linha(.26,-.19,.94,-.19)
        for i,(label,valor,unit,frac,cor) in enumerate((
                ('POTÊNCIA',dados.get('n1_rpm',0),'%',dados.get('n1_rpm',0)/100,CIANO),
                ('COMBUSTÍVEL',dados.get('combustivel',0),'KG',dados.get('combustivel',0)/4500,CIANO),
                ('TEMP. ÓLEO',dados.get('temperatura_oleo',0),'°C',dados.get('temperatura_oleo',0)/100,AMBAR))):
            y=-.25-i*.106
            self._texto(label,.27,y,.025,SUAVE)
            self._texto(f'{valor:.0f} {unit}',.77,y,.029,TEXTO)
            self._ret(L3_BARRA_X, y-.039, L3_BARRA_W, L3_BARRA_H, (.10,.16,.20))
            self._ret(L3_BARRA_X, y-.039, L3_BARRA_W * min(1,max(0,frac)), L3_BARRA_H, cor)
        nivel=dados.get('nivel_alerta',0)
        cor=VERMELHO if nivel>=2 else AMBAR if nivel else CIANO
        self._ret(L3_ALERTA_X, L3_ALERTA_Y, L3_ALERTA_W, L3_ALERTA_H, cor, .09)
        self._ret(L3_ALERTA_X, L3_ALERTA_Y, .004, L3_ALERTA_H, cor)
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

    def _botao(self,label,x,y,w,acao,ativo=False,cor_destaque=CIANO):
        cor_base = cor_destaque if ativo else BORDA
        self._ret(x,y,w,.058,cor_base,.32 if ativo else .18)
        if ativo:
            self._moldura(x,y,w,.058,cor_base)
        self._texto(label,x+.013,y+.029,.025,cor_destaque if ativo else SUAVE)
        return (x,y,w,.058,acao)

    def desenhar_hud_telemetria(self, estado):
        """Renderiza o HUD superior, botões operacionais e cartões de telemetria."""
        botoes = []
        estrategia = estado.get('estrategia', 'MULTICAMADA')
        simulacao_pausada = estado.get('simulacao_pausada', False)
        ajuda = estado.get('ajuda', False)
        fps_exibicao = estado.get('fps_exibicao', 0.0)
        tempo_frame_ms = estado.get('tempo_frame_ms', 0.0)
        vsync_ativado = estado.get('vsync_ativado', False)
        qtd_elementos = estado.get('qtd_elementos', 0)
        exibir_estresse = estado.get('exibir_estresse', False)
        proporcao_transparencia = estado.get('proporcao_transparencia', 0.5)
        num_camadas = estado.get('num_camadas', 4)
        camadas_visibilidade = estado.get('camadas_visibilidade', [True] * num_camadas)
        largura = estado.get('largura', 1280)
        altura = estado.get('altura', 800)
        cpu_exibicao = estado.get('cpu_exibicao', 0.0)
        ram_exibicao_mb = estado.get('ram_exibicao_mb', 0.0)
        gpu_nome = estado.get('gpu_nome', 'GPU')
        mensagem = estado.get('mensagem', '')
        tempos = estado.get('tempos', [])

        # Cabeçalho Superior
        self._ret(-1,.88,2,.12,FUNDO)
        self._linha(-1,.88,1,.88)
        self._circulo(-.94,.942,.028,CIANO)
        self._linha(-.96,.942,-.92,.942,CIANO,.003)
        self._texto('A E R I S',-.89,.944,.048,TEXTO)
        self._texto('ESTAÇÃO DE MONITORAMENTO AÉREO',-.64,.942,.024,SUAVE)
        self._circulo(.62,.944,.008,AMBAR if simulacao_pausada else CIANO,True)
        self._texto('PAUSADO' if simulacao_pausada else 'AO VIVO',.64,.944,.024,CIANO)
        self._texto('BR-07 / SIMULAÇÃO',.79,.944,.021,SUAVE)
        self._texto('Operação Serra do Mar',-.96,.817,.041,TEXTO)
        self._texto('Inspeção ambiental com drone  /  pesquisa em computação gráfica',-.96,.758,.024,SUAVE)

        # Botão Estratégia em destaque visual
        is_multi = (estrategia == 'MULTICAMADA')
        cor_estrategia = VERDE if is_multi else AMBAR
        lbl_estrategia = 'M  MULTICAMADA [FBOs]' if is_multi else 'M  MONOLÍTICA [DIRETO]'
        botoes.append(self._botao(lbl_estrategia, .01, .79, .33, 'modo', ativo=True, cor_destaque=cor_estrategia))

        botoes.append(self._botao('N  CENÁRIO', .36, .79, .20, 'cenario'))
        botoes.append(self._botao('PAUSA' if not simulacao_pausada else 'RETOMAR', .58, .79, .17, 'pausa', simulacao_pausada))
        botoes.append(self._botao('H  AJUDA', .77, .79, .20, 'ajuda', ajuda))

        # Quatro cartões de métricas inferiores
        titulo_card = 'MULTICAMADA (FBOs)' if is_multi else 'MONOLÍTICA (PASSE ÚNICO)'
        cards = ((-.97, 'DESEMPENHO'), (-.48, 'CARGA SINTÉTICA'), (.01, titulo_card), (.50, 'RECURSOS'))
        for x, label in cards:
            self._ret(x, -.915, .47, .165, PAINEL)
            self._texto(label, x + .02, -.783, .021, cor_estrategia if label == titulo_card else SUAVE)

        # Cartão 1: Desempenho
        self._texto(f'{fps_exibicao:.0f}', -.95, -.843, .058, CIANO)
        self._texto(f'FPS    {tempo_frame_ms:.2f} ms', -.83, -.850, .025, TEXTO)
        self._texto('V-SYNC ' + ('ON' if vsync_ativado else 'OFF'), -.95, -.894, .018, SUAVE)

        # Cartão 2: Carga Sintética
        carga = qtd_elementos if exibir_estresse else 0
        self._texto(f'{carga:,}', -.46, -.850, .047, TEXTO)
        botoes.append(self._botao('S  ' + ('ON' if exibir_estresse else 'OFF'), -.18, -.887, .15, 'estresse', exibir_estresse))
        self._texto(f'ALPHA {proporcao_transparencia:.0%}', -.46, -.894, .018, SUAVE)

        # Cartão 3: Pipeline e Camadas Semânticas
        if num_camadas == 4:
            labels_semanticos = ('F1 3D', 'F2 NAV', 'F3 PFD', 'F4 SYS')
            largura_btn = .082
            espaco = .085
        else:
            labels_semanticos = ('F1 3D+NAV', 'F2 PFD+SYS')
            largura_btn = .165
            espaco = .170

        for idx in range(num_camadas):
            lbl = labels_semanticos[idx] if idx < len(labels_semanticos) else f'L{idx+1}'
            ativo_camada = camadas_visibilidade[idx] if idx < len(camadas_visibilidade) else True
            botoes.append(self._botao(lbl, .02 + idx * espaco, -.903, largura_btn, f'camada:{idx}', ativo_camada))

        botoes.append(self._botao(f'C  {num_camadas}L', .370, -.903, .095, 'camadas', True))

        if is_multi:
            self._texto(f'{num_camadas} FBOs RGBA8 / {largura} × {altura}', .03, -.820, .022, VERDE)
        else:
            self._texto(f'Passe único direto / {largura} × {altura}', .03, -.820, .022, AMBAR)

        # Cartão 4: Recursos
        self._texto(f'CPU {cpu_exibicao:.0f}%    RAM {ram_exibicao_mb:.0f} MB', .52, -.838, .028, TEXTO)
        self._texto(gpu_nome[:32], .52, -.891, .019, SUAVE)

        # Barra de atalhos e mensagens de status
        self._texto('1–4  PRESETS    G  VISÃO 3D    I  INSTRUMENTOS    P  CAPTURA', -.96, -.964, .022, SUAVE)
        self._texto(mensagem[:65], .03, -.964, .022, CIANO)

        # Gráfico histórico de tempos de frame
        pontos = list(tempos)[-80:]
        if len(pontos) > 1:
            for j, (a, b) in enumerate(zip(pontos, pontos[1:])):
                x = -.75 + j * .24 / max(1, len(pontos) - 1)
                xx = -.75 + (j + 1) * .24 / max(1, len(pontos) - 1)
                self._linha(x, -.891 + min(a, 50) * .0011, xx, -.891 + min(b, 50) * .0011, CIANO, .0015, .65)

        return botoes

    def desenhar_ajuda(self):
        """Renderiza a sobreposição de ajuda com os comandos disponíveis."""
        self._ret(-1, -1, 2, 2, FUNDO, .86)
        self._ret(-.72, -.73, 1.44, 1.48, PAINEL)
        self._moldura(-.72, -.73, 1.44, 1.48)
        self._texto('CONTROLES DA ESTAÇÃO', -.65, .65, .049, TEXTO)
        self._texto('Explore a cena e compare o pipeline em tempo real.', -.65, .56, .029, SUAVE)
        linhas = (
            ('M', 'Alternar monolítica / multicamada'),
            ('1 / 2 / 3 / 4', 'Cargas C1 a C4, de 1 mil a 100 mil elementos'),
            ('S  /  ↑ ↓', 'Ativar carga / alterar quantidade de retângulos'),
            ('C  /  F1–F4', 'Usar 2 ou 4 camadas / alternar visibilidade (3D, NAV, PFD, SYS)'),
            ('T  /  V  /  R', 'Transparência / V-Sync / resolução'),
            ('G  /  I', 'Gaussianas 3D ou horizonte / instrumentos'),
            ('N  /  ESPAÇO', 'Cenário normal, tráfego, incêndio / pausar'),
            ('ARRASTAR / ROLAR', 'Orbitar e aproximar o terreno com o mouse'),
            ('HOME  /  P', 'Reiniciar simulação e câmera / salvar imagem'),
            ('H  /  ESC', 'Fechar ajuda / sair da aplicação')
        )
        for j, (tecla, acao) in enumerate(linhas):
            y = .43 - j * .102
            self._texto(tecla, -.65, y, .028, CIANO)
            self._texto(acao, -.23, y, .027, TEXTO)
        self._texto('Protótipo acadêmico • cenário e telemetria sintéticos', -.65, -.65, .024, SUAVE)
