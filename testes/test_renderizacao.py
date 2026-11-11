"""Regressões de renderização com contexto OpenGL real (janela invisível).

Execute: python -m unittest discover -s testes -v
Os testes são ignorados quando a máquina não disponibiliza OpenGL 3.3.
"""

import unittest
from unittest.mock import patch

import glfw
import moderngl
import numpy as np

from compositor import CompositorMulticamada
from pipeline import PipelineRenderizacao
from renderizador import PrimitiveBatch, FontAtlasRenderer, configurar_blending


class CenaTeste:
    """Texto inferior parcialmente coberto pela camada superior: detecta reordenação."""
    def __init__(self, batch, font):
        self.batch, self.font = batch, font
        self.hooks = []

    def renderizar_gpu(self, indice, total, dados):
        self.hooks.append((indice, total))

    def renderizar_camada(self, indice, total, dados, stress):
        if indice == 0:
            self.batch.adicionar_retangulo(-1, -1, 2, 2, 1, 0, 0, .5)
            self.font.desenhar_texto('Aviação: áçã', -.9, .55, .27, 1, 1, 1, .8)
        elif indice == 1:
            self.batch.adicionar_retangulo(-1, -1, 2, 2, 0, 1, 0, .5)
        elif indice == 2:
            self.batch.adicionar_retangulo(-.8, -.8, .4, .4, .1, .3, 1, .35)
        else:
            self.font.desenhar_texto('CAMADA 4', -.9, -.7, .2, 1, .8, .3, .75)


class TestRenderizacaoOpenGL(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not glfw.init():
            raise unittest.SkipTest('GLFW indisponível nesta máquina.')
        glfw.window_hint(glfw.VISIBLE, glfw.FALSE)
        glfw.window_hint(glfw.CONTEXT_VERSION_MAJOR, 3)
        glfw.window_hint(glfw.CONTEXT_VERSION_MINOR, 3)
        glfw.window_hint(glfw.OPENGL_PROFILE, glfw.OPENGL_CORE_PROFILE)
        cls.janela = glfw.create_window(96, 64, 'Teste de renderização', None, None)
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

    def _fbo(self, tamanho=(96, 64)):
        tex = self.ctx.texture(tamanho, 4, dtype='f1')
        fbo = self.ctx.framebuffer(color_attachments=[tex])
        self.addCleanup(tex.release)
        self.addCleanup(fbo.release)
        self.addCleanup(self.ctx.screen.use)
        return fbo

    @staticmethod
    def _pixels(fbo):
        return np.frombuffer(fbo.read(components=4, alignment=1), dtype=np.uint8).reshape(
            fbo.height, fbo.width, 4).copy()

    def test_alpha_equivalente_entre_estrategias_e_ordem_de_textos(self):
        fbo = self._fbo()
        for numero in (2, 4):
            with self.subTest(camadas=numero):
                with patch('pipeline.InterfaceAeronautica', CenaTeste):
                    pipeline = PipelineRenderizacao(self.ctx, 96, 64, numero)
                try:
                    pipeline.renderizar({}, 'Monolítica', destino=fbo)
                    monolitica = self._pixels(fbo)
                    pipeline.renderizar({}, 'Multicamada', destino=fbo)
                    multicamada = self._pixels(fbo)
                    diferenca = np.abs(monolitica.astype(int) - multicamada.astype(int))
                    # A passagem RGBA8 extra admite erro de arredondamento de um nível.
                    self.assertLessEqual(int(diferenca.max()), 2)
                    esperado = np.array([.255, .5075, .0175, 1]) * 255
                    np.testing.assert_allclose(multicamada[32, 48], esperado, atol=2)
                    self.assertEqual(len(pipeline.interface.hooks), numero * 2)
                finally:
                    pipeline.release()
                    pipeline.release()

    def test_visibilidade_igual_nas_duas_estrategias(self):
        fbo = self._fbo()
        with patch('pipeline.InterfaceAeronautica', CenaTeste):
            pipeline = PipelineRenderizacao(self.ctx, 96, 64, 4)
        self.addCleanup(pipeline.release)
        pipeline.renderizar({}, 'MONOLITICA', visibilidade=[False, True, False, False], destino=fbo)
        mono = self._pixels(fbo)
        pipeline.renderizar({}, 'MULTICAMADA', destino=fbo)
        np.testing.assert_allclose(self._pixels(fbo), mono, atol=1)
        self.assertEqual(pipeline.compositor.camadas_ativas, [False, True, False, False])

    def test_buffers_crescem_sem_perder_vertices(self):
        batch = PrimitiveBatch(self.ctx, max_vertices=6)
        self.addCleanup(batch.release)
        batch.adicionar_retangulo(-1, -1, 1, 1, 1, 0, 0, .5)
        primeiros = batch.buffer[:36].copy()
        batch.adicionar_retangulo(0, 0, 1, 1, 0, 1, 0, .5)
        batch.adicionar_triangulos_numpy(np.tile([0, 0, 1, 1, 1, 1], (30, 1)))
        self.assertEqual(batch.vertex_count, 42)
        self.assertGreaterEqual(batch.max_vertices, 42)
        np.testing.assert_array_equal(batch.buffer[:36], primeiros)
        fbo = self._fbo()
        fbo.use()
        self.ctx.viewport = (0, 0, *fbo.size)
        fbo.clear(0, 0, 0, 0)
        batch.renderizar()
        self.assertGreater(int(self._pixels(fbo).max()), 0)
        with self.assertRaises(ValueError):
            batch.adicionar_triangulos_numpy(np.zeros(7))
        batch.release()
        batch.release()

    def test_fonte_acento_aspecto_crescimento_e_alpha(self):
        fonte = FontAtlasRenderer(self.ctx, max_chars=1)
        self.addCleanup(fonte.release)
        fonte.set_viewport(96, 64)
        for caractere in 'áéíóúãõçÁÇ°':
            self.assertIn(caractere, fonte.char_uvs)
        largura, altura = fonte.medir_texto('Aviação', .25)
        fonte.set_viewport(192, 64)
        self.assertAlmostEqual(fonte.medir_texto('Aviação', .25)[0], largura/2)
        self.assertEqual(altura, .25)
        fonte.set_viewport(96, 64)
        fonte.desenhar_texto('AÇÃO', -.8, 0, .6, 1, .5, .25, .6)
        self.assertEqual(fonte.vertex_count, 24)
        self.assertGreaterEqual(fonte.max_chars, 4)
        fbo = self._fbo()
        fbo.use()
        self.ctx.viewport = (0, 0, *fbo.size)
        fbo.clear(0, 0, 0, 0)
        fonte.renderizar()
        pixels = self._pixels(fbo).astype(int)
        self.assertGreater(int(pixels[..., 3].max()), 100)
        self.assertLessEqual(int(np.abs(pixels[..., 0] - pixels[..., 3]).max()), 1)
        self.assertLessEqual(int(np.abs(pixels[..., 1] - pixels[..., 3]*.5).max()), 1)
        fonte.release()
        fonte.release()

    def test_opacidade_escala_rgb_e_alpha_sem_alpha_duplo(self):
        compositor = CompositorMulticamada(self.ctx, 96, 64, 2)
        self.addCleanup(compositor.release)
        compositor.limpar_camadas()
        compositor.obter_fbo(0).clear(.5, 0, 0, .5)
        fbo = self._fbo()
        compositor.compor(fbo, cor_fundo=(0, 0, 0, 0))
        np.testing.assert_allclose(self._pixels(fbo)[32, 48], [128, 0, 0, 128], atol=1)
        fbo.clear(0, 0, 0, 0)
        configurar_blending(self.ctx)
        compositor.texturas[0].use(0)
        compositor.prog_composite['u_opacity'].value = .5
        compositor.quad_vao.render(moderngl.TRIANGLES, vertices=6)
        np.testing.assert_allclose(self._pixels(fbo)[32, 48], [64, 0, 0, 64], atol=1)

    def test_redimensionamento_e_liberacao_idempotente(self):
        with patch('pipeline.InterfaceAeronautica', CenaTeste):
            pipeline = PipelineRenderizacao(self.ctx, 96, 64, 2)
        pipeline.redimensionar(128, 72)
        self.assertEqual(pipeline.compositor.obter_fbo(0).size, (128, 72))
        pipeline.definir_num_camadas(4)
        self.assertEqual(len(pipeline.compositor.fbos), 4)
        with self.assertRaises(ValueError):
            pipeline.redimensionar(0, 72)
        self.assertEqual((pipeline.largura, pipeline.altura), (128, 72))
        with self.assertRaises(ValueError):
            pipeline.definir_num_camadas(3)
        self.assertEqual(pipeline.num_camadas, 4)
        pipeline.release()
        pipeline.release()
        with self.assertRaises(RuntimeError):
            pipeline.renderizar({}, 'MONOLITICA')


if __name__ == '__main__':
    unittest.main()
