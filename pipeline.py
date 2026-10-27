"""Pipeline comum ao cockpit interativo e aos experimentos de desempenho.

As estratégias recebem os mesmos dados e preservam a mesma ordem de desenho.
Na estratégia monolítica há um único framebuffer de destino e nenhuma textura
intermediária; o flush por camada mantém textos e formas na ordem correta.
"""

import unicodedata

import moderngl

from compositor import CompositorMulticamada
from renderizador import PrimitiveBatch, FontAtlasRenderer, configurar_blending
from representacao import InterfaceAeronautica


class PipelineRenderizacao:
    COR_FUNDO = (0.02, 0.03, 0.07, 1.0)

    def __init__(self, ctx, largura, altura, num_camadas=4):
        self.ctx = ctx
        self.largura, self.altura = int(largura), int(altura)
        self.num_camadas = int(num_camadas)
        self._released = False
        self.compositor = CompositorMulticamada(ctx, largura, altura, num_camadas)
        self.batch = self.font = self.interface = None
        try:
            self.batch = PrimitiveBatch(ctx)
            self.font = FontAtlasRenderer(ctx)
            self.font.set_viewport(largura, altura)
            self.interface = InterfaceAeronautica(self.batch, self.font)
        except Exception:
            self.release()
            raise

    @staticmethod
    def _normalizar_estrategia(estrategia):
        nome = ''.join(ch for ch in unicodedata.normalize('NFD', str(estrategia))
                       if not unicodedata.combining(ch)).strip().upper()
        if nome not in ('MULTICAMADA', 'MONOLITICA'):
            raise ValueError('Estratégia inválida; use MULTICAMADA ou MONOLITICA.')
        return nome

    def redimensionar(self, largura, altura):
        self.compositor.redimensionar(largura, altura)
        self.largura, self.altura = int(largura), int(altura)
        self.font.set_viewport(largura, altura)

    def definir_num_camadas(self, num_camadas):
        self.compositor.definir_num_camadas(num_camadas)
        self.num_camadas = self.compositor.num_camadas

    def _desenhar_camada(self, indice, dados, stress_dict):
        self.batch.limpar()
        self.font.limpar()
        configurar_blending(self.ctx)
        hook_gpu = getattr(self.interface, 'renderizar_gpu', None)
        if callable(hook_gpu):
            hook_gpu(indice, self.num_camadas, dados)
            # Uma cena 3D pode usar viewport/clipping próprios; a simbologia usa
            # novamente a área completa e o contrato de composição 2D.
            self.ctx.viewport = (0, 0, self.largura, self.altura)
            self.ctx.scissor = None
            self.ctx.disable(moderngl.DEPTH_TEST | moderngl.CULL_FACE)
            configurar_blending(self.ctx)
        self.interface.renderizar_camada(indice, self.num_camadas, dados, stress_dict)
        self.batch.renderizar()
        self.font.renderizar()
        return self.batch.vertex_count, self.font.vertex_count

    def renderizar(self, dados, estrategia, num_camadas=None, visibilidade=None,
                   stress_dict=None, destino=None):
        """Desenha um frame e retorna contagens para inspeção e telemetria.

        ``destino`` pode ser um FBO RGBA8 para comparação visual e captura.
        ``visibilidade`` aceita uma sequência ou mapa com índices de camada.
        O chamador controla atualização da simulação, swap e sincronização GPU.
        """
        if self._released:
            raise RuntimeError('O pipeline já foi liberado.')
        estrategia = self._normalizar_estrategia(estrategia)
        if num_camadas is not None:
            self.definir_num_camadas(num_camadas)
        if visibilidade is None:
            ativas = list(self.compositor.camadas_ativas)
        elif hasattr(visibilidade, 'get'):
            ativas = [bool(visibilidade.get(i, True)) for i in range(self.num_camadas)]
        else:
            if len(visibilidade) < self.num_camadas:
                raise ValueError('Informe a visibilidade de todas as camadas físicas.')
            ativas = [bool(visibilidade[i]) for i in range(self.num_camadas)]
        self.compositor.camadas_ativas[:] = ativas
        if destino is None:
            destino = self.ctx.screen
        if destino is None:
            raise ValueError('Este contexto requer um framebuffer de destino explícito.')
        # ModernGL conserva o tamanho inicial da referência ao framebuffer
        # padrão após um resize GLFW. O tamanho real vem do callback da janela;
        # somente anexos offscreen possuem dimensões fixas e verificáveis aqui.
        if destino is not self.ctx.screen and tuple(destino.size) != (self.largura, self.altura):
            raise ValueError('O framebuffer de destino deve ter a resolução do pipeline.')
        stress_dict = {} if stress_dict is None else stress_dict
        self.ctx.disable(moderngl.DEPTH_TEST | moderngl.CULL_FACE)
        self.ctx.scissor = None
        self.ctx.viewport = (0, 0, self.largura, self.altura)
        configurar_blending(self.ctx)
        vertices, vertices_texto = 0, 0
        if estrategia == 'MULTICAMADA':
            self.compositor.limpar_camadas()
        else:
            destino.use()
            destino.clear(*self.COR_FUNDO)
        for indice, ativa in enumerate(ativas):
            if not ativa:
                continue
            if estrategia == 'MULTICAMADA':
                self.compositor.obter_fbo(indice).use()
            self.ctx.viewport = (0, 0, self.largura, self.altura)
            qtd, qtd_texto = self._desenhar_camada(indice, dados, stress_dict)
            vertices += qtd
            vertices_texto += qtd_texto
        if estrategia == 'MULTICAMADA':
            self.compositor.compor(destino, self.COR_FUNDO)
        return {'vertices': vertices, 'vertices_texto': vertices_texto,
                'camadas_ativas': sum(ativas), 'estrategia': estrategia}

    def release(self):
        if self._released:
            return
        self._released = True
        for recurso in (self.interface, self.font, self.batch, self.compositor):
            liberar = getattr(recurso, 'release', None)
            if callable(liberar):
                liberar()
