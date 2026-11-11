"""AERIS — estação interativa de monitoramento por drone, ModernGL 3.3.
Autores: Matheus Della Rosa (113209), Guilherme Marolla Tesch (113800).
"""
import argparse
from collections import deque
from datetime import datetime
import json
from pathlib import Path
import sys
import time

try:
    import glfw
    import moderngl
    import psutil
    from PIL import Image
except ModuleNotFoundError as erro:
    raise SystemExit(f'Dependência ausente: {erro.name}. Execute: python -m pip install -r requirements.txt') from erro

from configuracoes import obter_configuracoes
from pipeline import PipelineRenderizacao
from renderizador import configurar_blending
from representacao import FUNDO, PAINEL, BORDA, TEXTO, SUAVE, CIANO, AMBAR
from simulador import SimuladorVoo

RAIZ = Path(__file__).resolve().parent


class AplicacaoAeronautica:
    def __init__(self, largura=1280, altura=800, *, oculto=False, seed=42):
        self.largura,self.altura=largura,altura
        self.seed=seed
        self.estrategia='MULTICAMADA'
        self.num_camadas=4
        self.qtd_elementos=10000
        self.proporcao_transparencia=.5
        self.exibir_estresse=False
        self.camadas_visibilidade=[True]*4
        self.vsync_ativado=not oculto
        self.simulacao_pausada=False
        self.ajuda=False
        self.cenario='incendio'
        self.processo=psutil.Process()
        self.processo.cpu_percent()
        self.fps_exibicao=self.tempo_frame_ms=self.cpu_exibicao=self.ram_exibicao_mb=0
        self.tempos=deque(maxlen=180)
        self.botoes=[]
        self.arrastando=False
        self.ultima_posicao=None
        self.captura_pendente=None
        self.mensagem='Arraste o terreno para orbitar. Role para aproximar.'
        self.mensagem_ate=time.perf_counter()+8
        self.pipeline=self.ctx=self.window=None
        if not glfw.init():
            raise RuntimeError('Não foi possível inicializar o GLFW.')
        try:
            glfw.window_hint(glfw.CONTEXT_VERSION_MAJOR,3)
            glfw.window_hint(glfw.CONTEXT_VERSION_MINOR,3)
            glfw.window_hint(glfw.OPENGL_PROFILE,glfw.OPENGL_CORE_PROFILE)
            glfw.window_hint(glfw.VISIBLE,not oculto)
            glfw.window_hint(glfw.SAMPLES,0)
            self.window=glfw.create_window(largura,altura,'AERIS | Monitoramento aéreo e composição gráfica',None,None)
            if not self.window:
                raise RuntimeError('Não foi possível criar um contexto OpenGL 3.3.')
            glfw.make_context_current(self.window)
            glfw.swap_interval(int(self.vsync_ativado))
            glfw.set_window_size_limits(self.window,960,600,glfw.DONT_CARE,glfw.DONT_CARE)
            self.ctx=moderngl.create_context(require=330)
            self.largura,self.altura=glfw.get_framebuffer_size(self.window)
            self.pipeline=PipelineRenderizacao(self.ctx,self.largura,self.altura,self.num_camadas)
            self.batch=self.pipeline.batch
            self.font_rend=self.pipeline.font
            self.interface=self.pipeline.interface
            self.interface.seed_cena=seed
            self.compositor=self.pipeline.compositor
            self.simulador=SimuladorVoo(seed=seed)
            self.simulador.definir_cenario(self.cenario)
            self._atualizar_geometria_estresse()
            glfw.set_framebuffer_size_callback(self.window,self._tratar_redimensionamento)
            glfw.set_key_callback(self.window,self._tratar_teclado)
            glfw.set_mouse_button_callback(self.window,self._tratar_mouse)
            glfw.set_cursor_pos_callback(self.window,self._mover_mouse)
            glfw.set_scroll_callback(self.window,self._rolar_mouse)
        except Exception:
            self.encerrar()
            raise

    def _avisar(self,mensagem):
        self.mensagem=mensagem
        self.mensagem_ate=time.perf_counter()+4

    def _atualizar_geometria_estresse(self):
        self.stress_dict=self.interface.gerador.atualizar_elementos_estresse(
            self.qtd_elementos if self.exibir_estresse else 0,self.num_camadas,self.proporcao_transparencia,seed=self.seed)

    def _tratar_redimensionamento(self,window,largura,altura):
        if largura>0 and altura>0:
            self.largura,self.altura=largura,altura
            self.pipeline.redimensionar(largura,altura)

    def definir_num_camadas(self,n):
        self.pipeline.definir_num_camadas(n)
        self.num_camadas=n
        self.camadas_visibilidade=[True]*n
        self._atualizar_geometria_estresse()

    def aplicar_preset(self,config_id):
        config=obter_configuracoes([config_id])[0]
        self.qtd_elementos=config['elementos']
        self.exibir_estresse=True
        self.definir_num_camadas(config['camadas'])
        glfw.set_window_size(self.window,config['largura'],config['altura'])
        glfw.poll_events()
        self._tratar_redimensionamento(self.window,*glfw.get_framebuffer_size(self.window))
        self._avisar(f"{config_id}: {self.qtd_elementos:,} retângulos | {self.num_camadas} camadas")

    def _acao(self,acao):
        if acao=='modo':
            self.estrategia='MONOLITICA' if self.estrategia=='MULTICAMADA' else 'MULTICAMADA'
            desc='Composição em FBOs' if self.estrategia=='MULTICAMADA' else 'Passe único direto (0 FBOs)'
            self._avisar(f'Estratégia: {self.estrategia} ({desc})')
        elif acao=='pausa':
            self.simulacao_pausada=not self.simulacao_pausada
        elif acao=='estresse':
            self.exibir_estresse=not self.exibir_estresse
            self._atualizar_geometria_estresse()
        elif acao=='camadas':
            self.definir_num_camadas(2 if self.num_camadas==4 else 4)
            desc='2 grupos' if self.num_camadas==2 else '4 subsistemas'
            self._avisar(f'Camadas físicas: {self.num_camadas} ({desc})')
        elif acao=='alpha':
            self.proporcao_transparencia={0:.5,.5:.8,.8:0}[self.proporcao_transparencia]
            self._atualizar_geometria_estresse()
        elif acao=='gaussianas':
            self.interface.exibir_gaussianas=not self.interface.exibir_gaussianas
        elif acao=='instrumentos':
            self.interface.exibir_instrumentos=not self.interface.exibir_instrumentos
        elif acao=='ajuda':
            self.ajuda=not self.ajuda
        elif acao=='cenario':
            cenarios=('normal','trafego','incendio')
            self.cenario=cenarios[(cenarios.index(self.cenario)+1)%3]
            self.simulador.definir_cenario(self.cenario)
            self._avisar(f'Cenário: {self.cenario.upper()}')
        elif acao=='reiniciar':
            self.simulador.reiniciar()
            self.simulador.definir_cenario(self.cenario)
            if self.interface.cena:
                self.interface.cena.reiniciar_camera()
            self._avisar('Simulação e câmera reiniciadas')
        elif acao.startswith('camada:'):
            i=int(acao.split(':')[1])
            self.camadas_visibilidade[i]=not self.camadas_visibilidade[i]
            nomes_4=('L1 Terreno/3D','L2 Navegação','L3 Instrumentos','L4 Sistemas')
            nomes_2=('L1 Terreno+Nav','L2 Inst+Sistemas')
            nome=(nomes_2 if self.num_camadas==2 else nomes_4)[i]
            status='VISÍVEL' if self.camadas_visibilidade[i] else 'OCULTA'
            self._avisar(f'{nome}: {status}')
        elif acao.startswith('preset:'):
            self.aplicar_preset(acao.split(':')[1])
        elif acao=='captura':
            self.captura_pendente=RAIZ/'capturas'/f'aeris-{datetime.now():%Y%m%d-%H%M%S-%f}.png'
            self._avisar('Captura salva em capturas/')

    def _tratar_teclado(self,window,key,scancode,action,mods):
        if action not in (glfw.PRESS,glfw.REPEAT):
            return
        if key==glfw.KEY_ESCAPE and action==glfw.PRESS:
            if self.ajuda:
                self.ajuda=False
            else:
                glfw.set_window_should_close(window,True)
        if key in (glfw.KEY_UP,glfw.KEY_DOWN):
            self.qtd_elementos=max(0,min(200000,self.qtd_elementos+(5000 if key==glfw.KEY_UP else -5000)))
            self.exibir_estresse=True
            self._atualizar_geometria_estresse()
        if action!=glfw.PRESS:
            return
        mapa={glfw.KEY_M:'modo',glfw.KEY_SPACE:'pausa',glfw.KEY_S:'estresse',glfw.KEY_C:'camadas',
              glfw.KEY_T:'alpha',glfw.KEY_G:'gaussianas',glfw.KEY_I:'instrumentos',glfw.KEY_H:'ajuda',
              glfw.KEY_N:'cenario',glfw.KEY_HOME:'reiniciar',glfw.KEY_P:'captura'}
        if key in mapa:
            self._acao(mapa[key])
        elif glfw.KEY_1<=key<=glfw.KEY_4:
            self.aplicar_preset(f'C{key-glfw.KEY_1+1}')
        elif glfw.KEY_F1<=key<=glfw.KEY_F4 and key-glfw.KEY_F1<self.num_camadas:
            self._acao(f'camada:{key-glfw.KEY_F1}')
        elif key==glfw.KEY_V:
            self.vsync_ativado=not self.vsync_ativado
            glfw.swap_interval(int(self.vsync_ativado))
        elif key==glfw.KEY_R:
            w,h=(1920,1080) if self.largura<1900 else (1280,720)
            glfw.set_window_size(window,w,h)

    def _ndc_mouse(self):
        x,y=glfw.get_cursor_pos(self.window)
        w,h=glfw.get_window_size(self.window)
        return 2*x/max(1,w)-1,1-2*y/max(1,h)

    def _tratar_mouse(self,window,button,action,mods):
        if button!=glfw.MOUSE_BUTTON_LEFT:
            return
        if action==glfw.RELEASE:
            self.arrastando=False
            return
        x,y=self._ndc_mouse()
        if self.ajuda:
            if not (-.72<=x<=.72 and -.73<=y<=.75):
                self.ajuda=False
            return
        for bx,by,bw,bh,acao in reversed(self.botoes):
            if bx<=x<=bx+bw and by<=y<=by+bh:
                self._acao(acao)
                return
        self.arrastando=(-.95<x<.18 and -.59<y<.59 and not self.ajuda)
        self.ultima_posicao=glfw.get_cursor_pos(window)

    def _mover_mouse(self,window,x,y):
        if self.arrastando and self.interface.cena is not None:
            px,py=self.ultima_posicao
            self.interface.cena.azimute+=(x-px)*.25
            self.interface.cena.elevacao=max(8,min(82,self.interface.cena.elevacao+(y-py)*.20))
        self.ultima_posicao=(x,y)

    def _rolar_mouse(self,window,dx,dy):
        x,y=self._ndc_mouse()
        if -.95<x<.18 and -.59<y<.59 and self.interface.cena is not None and not self.ajuda:
            self.interface.cena.distancia=max(4,min(28,self.interface.cena.distancia*.90**dy))

    def _botao(self,label,x,y,w,acao,ativo=False):
        self.interface._ret(x,y,w,.058,CIANO if ativo else BORDA,.32 if ativo else .18)
        if ativo:
            self.interface._moldura(x,y,w,.058,CIANO)
        self.interface._texto(label,x+.013,y+.029,.025,CIANO if ativo else SUAVE)
        self.botoes.append((x,y,w,.058,acao))

    def desenhar_hud_telemetria(self):
        i=self.interface
        self.botoes=[]
        i._ret(-1,.88,2,.12,FUNDO)
        i._linha(-1,.88,1,.88)
        i._circulo(-.94,.942,.028,CIANO)
        i._linha(-.96,.942,-.92,.942,CIANO,.003)
        i._texto('A E R I S',-.89,.944,.048,TEXTO)
        i._texto('ESTAÇÃO DE MONITORAMENTO AÉREO',-.64,.942,.024,SUAVE)
        i._circulo(.62,.944,.008,AMBAR if self.simulacao_pausada else CIANO,True)
        i._texto('PAUSADO' if self.simulacao_pausada else 'AO VIVO',.64,.944,.024,CIANO)
        i._texto('BR-07 / SIMULAÇÃO',.79,.944,.021,SUAVE)
        i._texto('Operação Serra do Mar',-.96,.817,.041,TEXTO)
        i._texto('Inspeção ambiental com drone  /  pesquisa em computação gráfica',-.96,.758,.024,SUAVE)
        self._botao('M  '+('MULTICAMADA' if self.estrategia=='MULTICAMADA' else 'MONOLÍTICA'),.03,.79,.30,'modo',self.estrategia=='MULTICAMADA')
        self._botao('N  CENÁRIO',.35,.79,.21,'cenario')
        self._botao('PAUSA' if not self.simulacao_pausada else 'RETOMAR',.58,.79,.17,'pausa',self.simulacao_pausada)
        self._botao('H  AJUDA',.77,.79,.20,'ajuda',self.ajuda)
        # Quatro cartões de métricas, separados do conteúdo da missão.
        titulo_card='COMPOSIÇÃO (FBO)' if self.estrategia=='MULTICAMADA' else 'MONOLÍTICA (DIRETO)'
        cards=((- .97,'DESEMPENHO'),(-.48,'CARGA SINTÉTICA'),(.01,titulo_card),(.50,'RECURSOS'))
        for x,label in cards:
            i._ret(x,-.915,.47,.165,PAINEL)
            i._texto(label,x+.02,-.783,.021,SUAVE)
        i._texto(f'{self.fps_exibicao:.0f}',-.95,-.843,.058,CIANO)
        i._texto(f'FPS    {self.tempo_frame_ms:.2f} ms',-.83,-.850,.025,TEXTO)
        i._texto('V-SYNC '+('ON' if self.vsync_ativado else 'OFF'),-.95,-.894,.018,SUAVE)
        carga=self.qtd_elementos if self.exibir_estresse else 0
        i._texto(f'{carga:,}',-.46,-.850,.047,TEXTO)
        self._botao('S  '+('ON' if self.exibir_estresse else 'OFF'),-.18,-.887,.15,'estresse',self.exibir_estresse)
        i._texto(f'ALPHA {self.proporcao_transparencia:.0%}',-.46,-.894,.018,SUAVE)
        for idx in range(self.num_camadas):
            self._botao(f'L{idx+1}',.03+idx*.085,-.903,.075,f'camada:{idx}',self.camadas_visibilidade[idx])
        self._botao(f'C  {self.num_camadas}L',.370,-.903,.095,'camadas',True)
        if self.estrategia=='MULTICAMADA':
            i._texto(f'{self.num_camadas} FBOs RGBA8 / {self.largura} × {self.altura}',.03,-.820,.022,TEXTO)
        else:
            i._texto(f'Passe único na tela / {self.largura} × {self.altura}',.03,-.820,.022,TEXTO)
        i._texto(f'CPU {self.cpu_exibicao:.0f}%    RAM {self.ram_exibicao_mb:.0f} MB',.52,-.838,.028,TEXTO)
        gpu=self.ctx.info.get('GL_RENDERER','GPU')
        i._texto(gpu[:32],.52,-.891,.019,SUAVE)
        i._texto('1–4  PRESETS    G  VISÃO 3D    I  INSTRUMENTOS    P  CAPTURA',-.96,-.964,.022,SUAVE)
        mensagem=self.mensagem if time.perf_counter()<self.mensagem_ate else f'CENÁRIO: {self.cenario.upper()}  |  DADOS SINTÉTICOS'
        i._texto(mensagem[:65],.03,-.964,.022,CIANO)
        # Gráfico real dos últimos frames (sem incluir a própria coleta de CPU).
        pontos=list(self.tempos)[-80:]
        if len(pontos)>1:
            for j,(a,b) in enumerate(zip(pontos,pontos[1:])):
                x=-.75+j*.24/max(1,len(pontos)-1)
                xx=-.75+(j+1)*.24/max(1,len(pontos)-1)
                i._linha(x,-.891+min(a,50)*.0011,xx,-.891+min(b,50)*.0011,CIANO,.0015,.65)

    def desenhar_ajuda(self):
        i=self.interface
        i._ret(-1,-1,2,2,FUNDO,.86)
        i._ret(-.72,-.73,1.44,1.48,PAINEL)
        i._moldura(-.72,-.73,1.44,1.48)
        i._texto('CONTROLES DA ESTAÇÃO',-.65,.65,.049,TEXTO)
        i._texto('Explore a cena e compare o pipeline em tempo real.',-.65,.56,.029,SUAVE)
        linhas=(('M','Alternar monolítica / multicamada'),('1 / 2 / 3 / 4','Cargas C1 a C4, de 1 mil a 100 mil elementos'),
                ('S  /  ↑ ↓','Ativar carga / alterar quantidade de retângulos'),('C  /  F1–F4','Usar 2 ou 4 camadas / alternar visibilidade'),
                ('T  /  V  /  R','Transparência / V-Sync / resolução'),('G  /  I','Gaussianas 3D ou horizonte / instrumentos'),
                ('N  /  ESPAÇO','Cenário normal, tráfego, incêndio / pausar'),('ARRASTAR / ROLAR','Orbitar e aproximar o terreno com o mouse'),
                ('HOME  /  P','Reiniciar simulação e câmera / salvar imagem'),('H  /  ESC','Fechar ajuda / sair da aplicação'))
        for j,(tecla,acao) in enumerate(linhas):
            y=.43-j*.102
            i._texto(tecla,-.65,y,.028,CIANO)
            i._texto(acao,-.23,y,.027,TEXTO)
        i._texto('Protótipo acadêmico • cenário e telemetria sintéticos',-.65,-.65,.024,SUAVE)

    def salvar_captura(self,caminho):
        caminho=Path(caminho).resolve()
        caminho.parent.mkdir(parents=True,exist_ok=True)
        self.ctx.finish()
        # Alguns drivers rejeitam a seleção de attachment feita pelo read do
        # framebuffer padrão. Copie para RGBA8 e leia o anexo explícito; isso
        # também usa as dimensões atuais da janela depois de um resize GLFW.
        textura=self.ctx.texture((self.largura,self.altura),4,dtype='f1')
        snapshot=None
        try:
            snapshot=self.ctx.framebuffer(color_attachments=[textura])
            self.ctx.copy_framebuffer(snapshot,self.ctx.screen)
            pixels=snapshot.read(viewport=(0,0,self.largura,self.altura),components=3,alignment=1)
        finally:
            self.ctx.screen.use()
            self.ctx.viewport=(0,0,self.largura,self.altura)
            if snapshot is not None:
                snapshot.release()
            textura.release()
        imagem=Image.frombytes('RGB',(self.largura,self.altura),pixels)
        imagem.transpose(Image.Transpose.FLIP_TOP_BOTTOM).save(caminho)
        dados={'estrategia':self.estrategia,'cenario':self.cenario,'seed':self.seed,
               'camadas':self.num_camadas,'visibilidade':self.camadas_visibilidade,
               'elementos_sinteticos':self.qtd_elementos if self.exibir_estresse else 0,
               'resolucao':[self.largura,self.altura],'gpu':self.ctx.info.get('GL_RENDERER'),
               'simulacao':self.simulador.obter_dados()}
        caminho.with_suffix('.json').write_text(json.dumps(dados,ensure_ascii=False,indent=2),encoding='utf-8')
        print(f'Captura: {caminho}')

    def executar(self,max_frames=None,captura=None):
        ultimo=time.perf_counter()
        ultima_metrica=ultimo
        frames=0
        try:
            while not glfw.window_should_close(self.window):
                glfw.poll_events()
                if glfw.get_window_attrib(self.window,glfw.ICONIFIED):
                    glfw.wait_events_timeout(.1)
                    ultimo=time.perf_counter()
                    continue
                inicio=time.perf_counter()
                dt=1/60 if max_frames else min(.1,inicio-ultimo)
                ultimo=inicio
                if not self.simulacao_pausada:
                    self.simulador.atualizar(dt=dt)
                if self.tempos:
                    self.tempo_frame_ms=sum(self.tempos)/len(self.tempos)
                    self.fps_exibicao=1000/max(.001,self.tempo_frame_ms)
                if inicio-ultima_metrica>=.25 or frames==0:
                    self.cpu_exibicao=self.processo.cpu_percent()
                    self.ram_exibicao_mb=self.processo.memory_info().rss/1048576
                    ultima_metrica=inicio
                self.pipeline.renderizar(self.simulador.obter_dados(),self.estrategia,
                    visibilidade=self.camadas_visibilidade,stress_dict=self.stress_dict)
                self.ctx.screen.use()
                self.ctx.viewport=(0,0,self.largura,self.altura)
                configurar_blending(self.ctx)
                self.batch.limpar()
                self.font_rend.limpar()
                self.desenhar_hud_telemetria()
                self.batch.renderizar()
                self.font_rend.renderizar()
                if self.ajuda:
                    self.batch.limpar()
                    self.font_rend.limpar()
                    self.desenhar_ajuda()
                    self.batch.renderizar()
                    self.font_rend.renderizar()
                frames+=1
                if self.captura_pendente or (captura and max_frames and frames>=max_frames):
                    self.salvar_captura(self.captura_pendente or captura)
                    self.captura_pendente=None
                glfw.swap_buffers(self.window)
                fim=time.perf_counter()
                self.tempos.append((fim-inicio)*1000)
                if max_frames and frames>=max_frames:
                    break
        finally:
            self.encerrar()

    def encerrar(self):
        if self.pipeline is not None:
            self.pipeline.release()
            self.pipeline=None
        if self.ctx is not None:
            self.ctx.release()
            self.ctx=None
        if self.window is not None:
            glfw.destroy_window(self.window)
            self.window=None
        glfw.terminate()


def main(argv=None):
    argv=sys.argv[1:] if argv is None else list(argv)
    if '--benchmark' in argv or '-b' in argv:
        from benchmark import main as benchmark_main
        return benchmark_main([a for a in argv if a not in ('--benchmark','-b')])
    parser=argparse.ArgumentParser(description='AERIS: estação de drone e laboratório de composição gráfica.')
    parser.add_argument('--largura',type=int,default=1280)
    parser.add_argument('--altura',type=int,default=800)
    parser.add_argument('--seed',type=int,default=42)
    parser.add_argument('--gaussianas',type=int,default=6000,help='Quantidade de Gaussianas 3D da missão.')
    parser.add_argument('--oculto',action='store_true',help='Executa em janela invisível para validação.')
    parser.add_argument('--frames',type=int,help='Encerra após N frames, com passo de simulação fixo.')
    parser.add_argument('--captura',type=Path,help='Salva PNG e metadados JSON ao final.')
    parser.add_argument('--preset',choices=('C1','C2','C3','C4'))
    parser.add_argument('--estrategia',choices=('MULTICAMADA','MONOLITICA'),default='MULTICAMADA')
    parser.add_argument('--cenario',choices=('normal','trafego','incendio'),default='incendio')
    parser.add_argument('--sem-estresse',action='store_true')
    args=parser.parse_args(argv)
    if args.largura<960 or args.altura<600:
        parser.error('A janela precisa ter pelo menos 960 × 600 pixels.')
    if args.frames is not None and args.frames<1:
        parser.error('--frames deve ser positivo.')
    if args.gaussianas<1 or args.seed<0:
        parser.error('--gaussianas deve ser positivo e --seed não negativo.')
    app=AplicacaoAeronautica(args.largura,args.altura,oculto=args.oculto,seed=args.seed)
    app.interface.quantidade_gaussianas=args.gaussianas
    if args.preset:
        app.aplicar_preset(args.preset)
    if args.sem_estresse:
        app.exibir_estresse=False
        app._atualizar_geometria_estresse()
    app.estrategia=args.estrategia
    app.cenario=args.cenario
    app.simulador.definir_cenario(args.cenario)
    app.executar(max_frames=args.frames or (8 if args.captura else None),captura=args.captura)


if __name__=='__main__':
    main()
