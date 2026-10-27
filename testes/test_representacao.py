"""Contagem, alpha e reprodutibilidade da carga sintética, sem contexto GL."""

import random
import unittest

import numpy as np

from representacao import GeradorPrimitivas


class GeradorPrimitivasTests(unittest.TestCase):
    def test_resto_distribuido_sem_perder_elementos(self):
        for camadas, esperado in ((2, [4, 3]), (4, [2, 2, 2, 1])):
            with self.subTest(camadas=camadas):
                dados = GeradorPrimitivas().atualizar_elementos_estresse(7, camadas)
                self.assertEqual(set(dados), set(range(camadas)))
                self.assertEqual([dados[i].size // 36 for i in range(camadas)], esperado)
                self.assertEqual(sum(vertices.size // 36 for vertices in dados.values()), 7)
                for vertices in dados.values():
                    self.assertEqual(vertices.dtype, np.dtype("float32"))
                    self.assertTrue(vertices.flags.c_contiguous)
                    self.assertTrue(np.isfinite(vertices).all())
                    self.assertEqual(vertices.size % 36, 0)

    def test_seed_local_nao_altera_rng_global(self):
        estado_numpy = np.random.get_state()
        estado_python = random.getstate()
        try:
            np.random.seed(123)
            random.seed(123)
            esperados_numpy = np.random.random(8)
            esperados_python = [random.random() for _ in range(8)]
            np.random.seed(123)
            random.seed(123)
            GeradorPrimitivas(seed=99).atualizar_elementos_estresse(17, 4, .5)
            np.testing.assert_array_equal(np.random.random(8), esperados_numpy)
            self.assertEqual([random.random() for _ in range(8)], esperados_python)
        finally:
            np.random.set_state(estado_numpy)
            random.setstate(estado_python)

    def test_mesma_seed_reproduz_geometria_e_seed_diferente_altera(self):
        primeiro = GeradorPrimitivas(seed=42).atualizar_elementos_estresse(7, 4)
        segundo = GeradorPrimitivas(seed=42).atualizar_elementos_estresse(7, 4)
        outro = GeradorPrimitivas(seed=43).atualizar_elementos_estresse(7, 4)
        for camada in primeiro:
            np.testing.assert_array_equal(primeiro[camada], segundo[camada])
        self.assertTrue(any(not np.array_equal(primeiro[c], outro[c]) for c in primeiro))

    def test_seed_explicita_tambem_invalida_cache(self):
        gerador = GeradorPrimitivas(seed=42)
        primeiro = gerador.atualizar_elementos_estresse(7, 2, seed=1)
        segundo = gerador.atualizar_elementos_estresse(7, 2, seed=2)
        self.assertIsNot(primeiro, segundo)
        self.assertFalse(np.array_equal(primeiro[0], segundo[0]))
        self.assertIs(segundo, gerador.atualizar_elementos_estresse(7, 2, seed=2))

    def test_cache_invalida_apos_zero_e_troca_de_camadas(self):
        gerador = GeradorPrimitivas()
        inicial = gerador.atualizar_elementos_estresse(7, 2)
        self.assertIs(inicial, gerador.atualizar_elementos_estresse(7, 2))
        vazio = gerador.atualizar_elementos_estresse(0, 2)
        self.assertEqual(set(vazio), {0, 1})
        self.assertTrue(all(vertices.size == 0 for vertices in vazio.values()))
        quatro_vazias = gerador.atualizar_elementos_estresse(0, 4)
        self.assertIsNot(vazio, quatro_vazias)
        self.assertEqual(set(quatro_vazias), {0, 1, 2, 3})
        quatro = gerador.atualizar_elementos_estresse(7, 4)
        self.assertEqual(sum(vertices.size for vertices in quatro.values()), 7 * 36)
        volta = gerador.atualizar_elementos_estresse(7, 2)
        self.assertIsNot(volta, inicial)
        for camada in inicial:
            np.testing.assert_array_equal(volta[camada], inicial[camada])

    def test_transparencia_extremos_e_alpha_por_primitiva(self):
        gerador = GeradorPrimitivas()
        for proporcao in (0.0, 1.0):
            with self.subTest(proporcao=proporcao):
                dados = gerador.atualizar_elementos_estresse(7, 4, proporcao)
                for vertices in dados.values():
                    alphas = vertices.reshape(-1, 6, 6)[:, :, 5]
                    np.testing.assert_array_equal(alphas, np.repeat(alphas[:, :1], 6, axis=1))
                    if proporcao == 0:
                        np.testing.assert_array_equal(alphas, 1.0)
                    else:
                        self.assertTrue(np.all((alphas >= .15) & (alphas <= .55)))

    def test_fracao_transparente_definida_por_camada(self):
        # Cada camada seleciona round(n * proporção) retângulos transparentes.
        dados = GeradorPrimitivas().atualizar_elementos_estresse(7, 2, .5)
        for vertices in dados.values():
            alphas = vertices.reshape(-1, 6, 6)[:, 0, 5]
            self.assertEqual(np.count_nonzero(alphas < 1), round(len(alphas) * .5))

    def test_argumentos_invalidos_geram_value_error(self):
        invalidos = {
            "qtd": (-1, 1.5, 7.0, True, None, "7", np.nan, np.inf),
            "camadas": (0, 1, 3, 5, True, None, "2", 2.0, np.nan),
            "proporcao": (-.1, 1.1, True, None, "0.5", np.nan, np.inf),
            "seed": (-1, 1.5, True, "42", np.nan, np.inf),
        }
        for nome, valores in invalidos.items():
            for valor in valores:
                argumentos = {"qtd_total": 7, "num_camadas": 2, "proporcao_transparencia": .5, "seed": 42}
                chave = {"qtd": "qtd_total", "camadas": "num_camadas", "proporcao": "proporcao_transparencia", "seed": "seed"}[nome]
                argumentos[chave] = valor
                with self.subTest(nome=nome, valor=valor), self.assertRaises(ValueError):
                    GeradorPrimitivas().atualizar_elementos_estresse(**argumentos)

    def test_aceita_escalares_inteiros_numpy(self):
        dados = GeradorPrimitivas(seed=np.int64(42)).atualizar_elementos_estresse(
            np.int64(7), np.int64(4), np.float32(.5),
        )
        self.assertEqual(sum(vertices.size for vertices in dados.values()), 7 * 36)


if __name__ == "__main__":
    unittest.main()
