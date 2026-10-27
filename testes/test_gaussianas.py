"""Verificação numérica do splatting sem janela ou GPU."""

import unittest
import numpy as np

from gaussianas import (
    _CacheInstanciasGaussianas, _empacotar_instancias,
    gerar_cena_sintetica, matriz_camera, projetar_gaussianas,
)


class TestProjecaoGaussianas(unittest.TestCase):
    def projetar(self, centros, cov=None, **kwargs):
        centros = np.asarray(centros, dtype=float).reshape(-1, 3)
        if cov is None:
            cov = np.repeat(np.eye(3)[None] * 0.01, len(centros), axis=0)
        cores = np.ones((len(centros), 4))
        return projetar_gaussianas(centros, cov, cores, **kwargs)

    def test_perspectiva_covariancia_e_distancia(self):
        p = self.projetar([[0, 0, -2], [0, 0, -4]], fov_y=90, aspecto=1)
        np.testing.assert_array_equal(p.indices, [1, 0])
        np.testing.assert_allclose(p.centros_ndc, 0, atol=1e-12)
        # Dobrar a distância reduz o desvio padrão à metade e a variância a 1/4.
        np.testing.assert_allclose(p.covariancias_ndc[0], p.covariancias_ndc[1] / 4)
        np.testing.assert_allclose(p.covariancias_ndc[1], np.eye(2) * 0.0025)

    def test_ordenacao_back_to_front_estavel(self):
        p = self.projetar([[0, 0, -3], [0, 0, -8], [0, 0, -3], [0, 0, -5]])
        np.testing.assert_array_equal(p.indices, [1, 3, 0, 2])
        np.testing.assert_array_equal(p.profundidades, [8, 5, 3, 3])

    def test_near_far_atras_camera_e_frustum(self):
        p = self.projetar([[0, 0, -2], [0, 0, 2], [0, 0, -0.01],
                           [100, 0, -2], [0, 100, -2], [0, 0, -200]])
        np.testing.assert_array_equal(p.indices, [0])

    def test_suporte_intersectando_borda_nao_desaparece(self):
        # Centro fora do frustum; parte do suporte 3 sigma permanece visível.
        p = self.projetar([[2.1, 0, -2]], fov_y=90, aspecto=1)
        self.assertEqual(len(p), 1)
        self.assertGreater(p.centros_ndc[0, 0], 1)

    def test_covariancia_anisotropica_rotacionada(self):
        angulo = np.pi / 4
        r = np.array([[np.cos(angulo), -np.sin(angulo), 0],
                      [np.sin(angulo), np.cos(angulo), 0], [0, 0, 1]])
        cov = (r @ np.diag([0.16, 0.01, 0.01]) @ r.T)[None]
        p = self.projetar([[0, 0, -2]], cov, fov_y=90, aspecto=1)
        self.assertGreater(p.covariancias_ndc[0, 0, 1], 0.01)
        np.testing.assert_allclose(np.linalg.eigvalsh(p.covariancias_ndc[0]), [0.0025, 0.04])

    def test_camera_view_centraliza_alvo(self):
        view = matriz_camera([4, 3, 8], alvo=[0, 1, 0])
        p = self.projetar([[0, 1, 0]], view=view)
        np.testing.assert_allclose(p.centros_ndc, 0, atol=1e-12)
        np.testing.assert_allclose(view[:3, :3] @ view[:3, :3].T, np.eye(3), atol=1e-12)

    def test_cena_vazia_e_todos_rejeitados(self):
        for centros in ([], [[0, 0, 2]]):
            p = self.projetar(centros)
            self.assertEqual(len(p), 0)
            self.assertEqual(p.centros_ndc.shape, (0, 2))
            self.assertEqual(p.covariancias_ndc.shape, (0, 2, 2))

    def test_nao_finitos_e_covariancia_invalida_sao_descartados(self):
        cov = np.repeat(np.eye(3)[None] * 0.01, 4, axis=0)
        cov[1, 0, 0] = np.nan
        cov[2, 1, 1] = -1
        p = self.projetar([[0, 0, -2]] * 4, cov)
        np.testing.assert_array_equal(p.indices, [0, 3])
        for arr in (p.centros_ndc, p.covariancias_ndc, p.cores, p.profundidades):
            self.assertTrue(np.isfinite(arr).all())

    def test_entrada_invalida(self):
        for camera in ({"near": 0}, {"near": 2, "far": 1}, {"fov_y": 180}, {"aspecto": 0}):
            with self.assertRaises(ValueError):
                self.projetar([[0, 0, -2]], **camera)
        with self.assertRaises(ValueError):
            matriz_camera([0, 0, 0], [0, 0, 0])


class TestCenaSintetica(unittest.TestCase):
    def test_seed_local_covariancias_e_quantidade(self):
        estado_global = np.random.get_state()
        a = gerar_cena_sintetica(1000, seed=42)
        b = gerar_cena_sintetica(1000, seed=42)
        c = gerar_cena_sintetica(1000, seed=43)
        for arr_a, arr_b in zip(a, b):
            np.testing.assert_array_equal(arr_a, arr_b)
        self.assertFalse(np.array_equal(a[0], c[0]))
        self.assertEqual(a[0].shape, (1000, 3))
        self.assertTrue((np.linalg.eigvalsh(a[1]) > 0).all())
        self.assertEqual(set(a[3]), {0, 1, 2})
        self.assertTrue(all(np.isfinite(arr).all() for arr in a))
        estado_depois = np.random.get_state()
        for item_antes, item_depois in zip(estado_global, estado_depois):
            np.testing.assert_array_equal(item_antes, item_depois)


class TestCacheInstancias(unittest.TestCase):
    def setUp(self):
        self.cena = gerar_cena_sintetica(900, seed=42)
        self.cache = _CacheInstanciasGaussianas(*self.cena)

    def referencia_integral(self, view, tamanho, tempo, incendio):
        centros, cov, cores, tipos = self.cena
        centros, cores = centros.copy(), cores.copy()
        if incendio:
            fumaca = tipos == 1
            centros[fumaca, 0] += 0.10 * np.sin(tempo * 0.4 + self.cena[0][fumaca, 1])
            centros[fumaca, 2] += 0.06 * np.sin(tempo * 0.28 + self.cena[0][fumaca, 1])
            fogo = tipos == 2
            cores[fogo, 3] *= 0.88 + 0.12 * np.sin(tempo * 4 + self.cena[0][fogo, 0] * 12)
        else:
            cores[tipos > 0, 3] = 0
        projecao = projetar_gaussianas(
            centros, cov, cores, view, aspecto=tamanho[0] / tamanho[1], near=0.2, far=80,
        )
        return _empacotar_instancias(projecao, tamanho), projecao.indices

    def test_equivalencia_com_reprojecao_integral_em_multiplas_vistas(self):
        for pos in ([4, 6, 9], [-4, 2, 4], [1.2, 1.5, 1.4]):
            view = matriz_camera(pos, [0, 0.5, 0])
            for tamanho in ((723, 458), (1080, 700)):
                for tempo, incendio in ((0, True), (5.25, True), (40, False), (40, True)):
                    with self.subTest(pos=pos, tamanho=tamanho, tempo=tempo, incendio=incendio):
                        esperado, indices = self.referencia_integral(view, tamanho, tempo, incendio)
                        obtido = self.cache.preparar(view, tamanho, tempo, incendio)
                        np.testing.assert_array_equal(self.cache.indices_ordenados, indices)
                        np.testing.assert_allclose(obtido, esperado, rtol=2e-6, atol=2e-7)

    def test_reutiliza_terreno_e_frame_pausado_sem_recalcular(self):
        view = matriz_camera([4, 6, 9])
        a = self.cache.preparar(view, (700, 450), tempo=0)
        self.assertEqual(self.cache.reprojecoes_estaticas, 1)
        self.assertEqual(self.cache.reprojecoes_dinamicas, 1)
        self.assertIs(a, self.cache.preparar(view, (700, 450), tempo=0))
        self.assertEqual(self.cache.reprojecoes_dinamicas, 1)
        self.cache.preparar(view, (700, 450), tempo=1)
        self.assertEqual(self.cache.reprojecoes_estaticas, 1)
        self.assertEqual(self.cache.reprojecoes_dinamicas, 2)
        normal = self.cache.preparar(view, (700, 450), tempo=10, incendio=False)
        self.assertIs(normal, self.cache.preparar(view, (700, 450), tempo=20, incendio=False))
        self.assertEqual(self.cache.reprojecoes_estaticas, 1)
        self.assertEqual(self.cache.reprojecoes_dinamicas, 2)

    def test_camera_e_resolucao_invalidam_cache(self):
        view = matriz_camera([4, 6, 9])
        self.cache.preparar(view, (700, 450))
        self.cache.preparar(matriz_camera([-4, 6, 9]), (700, 450))
        self.assertEqual(self.cache.reprojecoes_estaticas, 2)
        self.cache.preparar(view, (1400, 900))
        self.assertEqual(self.cache.reprojecoes_estaticas, 3)

    def test_empate_de_profundidade_preserva_ids_entre_grupos(self):
        centros = np.array([[0, 0, -4]] * 3, dtype=float)
        cov = np.repeat(np.eye(3)[None] * 0.01, 3, axis=0)
        cache = _CacheInstanciasGaussianas(centros, cov, np.ones((3, 4)), np.array([0, 1, 2]))
        cache.preparar(np.eye(4), (700, 450), tempo=0)
        np.testing.assert_array_equal(cache.indices_ordenados, [0, 1, 2])


if __name__ == "__main__":
    unittest.main()
