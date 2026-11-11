"""Compara os pixels da cena completa usando os dois caminhos OpenGL reais.

FBOs RGBA8 introduzem arredondamento a cada passe: a estratégia multicamada
arredonda também cada grupo antes da composição final. São permitidos até
3 níveis por canal (de 255), com erro médio menor que meio nível; a tolerância
não permite diferenças de ordem, enquadramento ou transparência dupla.
"""

import unittest

import glfw
import moderngl
import numpy as np

from pipeline import PipelineRenderizacao
from simulador import SimuladorVoo


class TestIntegracaoCenaReal(unittest.TestCase):
    metricas = []

    @classmethod
    def setUpClass(cls):
        if not glfw.init():
            raise unittest.SkipTest('GLFW indisponível nesta máquina.')
        glfw.window_hint(glfw.VISIBLE, glfw.FALSE)
        glfw.window_hint(glfw.CONTEXT_VERSION_MAJOR, 3)
        glfw.window_hint(glfw.CONTEXT_VERSION_MINOR, 3)
        glfw.window_hint(glfw.OPENGL_PROFILE, glfw.OPENGL_CORE_PROFILE)
        cls.janela = glfw.create_window(320, 240, 'Integração AERIS', None, None)
        if not cls.janela:
            glfw.terminate()
            raise unittest.SkipTest('OpenGL 3.3 indisponível nesta máquina.')
        glfw.make_context_current(cls.janela)
        cls.ctx = moderngl.create_context(require=330)

    @classmethod
    def tearDownClass(cls):
        cls.ctx.release()
        glfw.destroy_window(cls.janela)
        glfw.terminate()

    def setUp(self):
        glfw.make_context_current(self.janela)
        self.pipeline = PipelineRenderizacao(self.ctx, 320, 240, 4)
        self.addCleanup(self.pipeline.release)
        self.tex = self.ctx.texture((320, 240), 4, dtype='f1')
        self.addCleanup(self.tex.release)
        self.fbo = self.ctx.framebuffer(color_attachments=[self.tex])
        self.addCleanup(self.fbo.release)
        # ModernGL guarda o último FBO ligado no contexto. Volte ao padrão
        # antes de destruir o alvo externo para não restaurar um nome excluído.
        self.addCleanup(self.ctx.screen.use)

    def _comparar(self, dados, camadas, visibilidade=None, stress=None):
        imagens = []
        for estrategia in ('MONOLITICA', 'MULTICAMADA'):
            self.pipeline.renderizar(dados, estrategia, num_camadas=camadas,
                                     visibilidade=visibilidade, stress_dict=stress,
                                     destino=self.fbo)
            imagens.append(np.frombuffer(self.fbo.read(components=4, alignment=1),
                                         dtype=np.uint8).reshape(240, 320, 4).copy())
            self.assertEqual(self.ctx.error, 'GL_NO_ERROR')
            self.assertEqual(self.ctx.viewport, (0, 0, 320, 240))
            # Um alfa final opaco pode arredondar para 254 em bordas subpixel
            # na mistura do driver; nunca deve perder mais que um nível RGBA8.
            self.assertGreaterEqual(int(imagens[-1][..., 3].min()), 254)
        diferenca = np.abs(imagens[0].astype(np.int16) - imagens[1].astype(np.int16))
        maximo, media = int(diferenca.max()), float(diferenca.mean())
        p99 = float(np.percentile(diferenca, 99))
        type(self).metricas.append((dados['cenario'], camadas, maximo, media, p99))
        self.assertLessEqual(maximo, 3, f'Erro máximo inesperado: {maximo}/255.')
        self.assertLessEqual(p99, 2, f'Erro p99 inesperado: {p99}/255.')
        self.assertLess(media, .5, f'Erro médio inesperado: {media}/255.')
        return imagens[1]

    def test_tres_cenarios_com_duas_e_quatro_camadas_e_transparencia(self):
        for cenario in ('normal', 'trafego', 'incendio'):
            simulador = SimuladorVoo(seed=123, cenario=cenario)
            for _ in range(8):
                simulador.atualizar(1/60)
            dados = simulador.obter_dados()
            for camadas in (2, 4):
                with self.subTest(cenario=cenario, camadas=camadas):
                    stress = self.pipeline.interface.gerador.atualizar_elementos_estresse(
                        1000, camadas, .8)
                    imagem = self._comparar(dados, camadas, [True]*camadas, stress)
                    self.assertGreater(float(imagem[..., :3].std()), 10)
                    self.assertIsNotNone(self.pipeline.interface.cena)
                    self.assertGreater(self.pipeline.interface.cena.quantidade_visivel, 100)

    def test_ocultar_camadas_inclusive_cena_3d(self):
        dados = SimuladorVoo(seed=123, cenario='incendio').obter_dados()
        for camadas in (2, 4):
            for visibilidade in ([False]+[True]*(camadas-1),
                                 [True]+[False]*(camadas-1), [False]*camadas):
                with self.subTest(camadas=camadas, visibilidade=visibilidade):
                    imagem = self._comparar(dados, camadas, visibilidade)
                    if not any(visibilidade):
                        esperado = np.array(self.pipeline.COR_FUNDO)*255
                        np.testing.assert_allclose(imagem[120, 160], esperado, atol=1)

    def test_horizonte_alternativo_resize_e_camera_orbital(self):
        dados = SimuladorVoo(seed=123, cenario='normal').obter_dados()
        self._comparar(dados, 4, [True]*4)
        cena = self.pipeline.interface.cena
        cena.azimute += 35
        cena.elevacao += 12
        cena.distancia *= .8
        orbital = self._comparar(dados, 4, [True]*4)
        cena.reiniciar_camera()
        reiniciada = self._comparar(dados, 4, [True]*4)
        self.assertGreater(float(np.abs(orbital.astype(int)-reiniciada.astype(int)).mean()), .2)
        self.pipeline.interface.exibir_gaussianas = False
        self._comparar(dados, 2, [True]*2)
        self._comparar(dados, 4, [True]*4)
        self.pipeline.redimensionar(640, 480)
        self.assertEqual(self.pipeline.compositor.obter_fbo(0).size, (640, 480))
        self.pipeline.redimensionar(320, 240)
        self._comparar(dados, 4, [True]*4)

    def test_redimensionar_janela_padrao_sem_anexo_offscreen(self):
        dados = SimuladorVoo(seed=123).obter_dados()
        textura = snapshot = None
        try:
            glfw.set_window_size(self.janela, 640, 480)
            glfw.poll_events()
            largura, altura = glfw.get_framebuffer_size(self.janela)
            self.pipeline.redimensionar(largura, altura)
            textura = self.ctx.texture((largura, altura), 4, dtype='f1')
            snapshot = self.ctx.framebuffer(color_attachments=[textura])
            for estrategia in ('MONOLITICA', 'MULTICAMADA'):
                self.pipeline.renderizar(dados, estrategia, visibilidade=[True]*4)
                self.assertEqual(self.ctx.error, 'GL_NO_ERROR')
                # A leitura direta do FBO padrão no driver AMD gera erro em
                # ModernGL mesmo sem resize. Um blit mantém o caminho portátil.
                self.ctx.copy_framebuffer(snapshot, self.ctx.screen)
                pixels = snapshot.read(viewport=(0, 0, largura, altura),
                                       components=3, alignment=1)
                self.assertEqual(len(pixels), largura * altura * 3)
                imagem = np.frombuffer(pixels, dtype=np.uint8).reshape(altura, largura, 3)
                self.assertGreater(float(imagem.std()), 10)
                self.assertEqual(self.ctx.error, 'GL_NO_ERROR')
        finally:
            self.ctx.screen.use()
            if snapshot is not None:
                snapshot.release()
            if textura is not None:
                textura.release()
            glfw.set_window_size(self.janela, 320, 240)
            glfw.poll_events()
            self.pipeline.redimensionar(320, 240)


if __name__ == '__main__':
    unittest.main()
