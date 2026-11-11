"""Contratos de reprodução para comparações experimentais justas."""

import random
import unittest
from unittest.mock import patch

from simulador import SimuladorVoo


class TestSimuladorVoo(unittest.TestCase):
    def test_mesma_seed_mesmos_passos(self):
        a, b = SimuladorVoo(seed=42), SimuladorVoo(seed=42)
        for _ in range(120):
            a.atualizar(1 / 60)
            b.atualizar(1 / 60)
        self.assertEqual(a.obter_dados(), b.obter_dados())
        outro = SimuladorVoo(seed=43)
        for _ in range(120):
            outro.atualizar(1 / 60)
        self.assertNotEqual(a.obter_dados(), outro.obter_dados())

    def test_pausa_nao_avanca_nem_rng(self):
        a, b = SimuladorVoo(), SimuladorVoo()
        antes, rng = a.obter_dados(), a._rng.getstate()
        for _ in range(50):
            a.atualizar(0)
        self.assertEqual(antes, a.obter_dados())
        self.assertEqual(rng, a._rng.getstate())
        a.atualizar(1 / 60)
        b.atualizar(1 / 60)
        self.assertEqual(a.obter_dados(), b.obter_dados())

    def test_reiniciar_reproduz_trajetoria(self):
        sim = SimuladorVoo(seed=7, cenario="incendio")
        inicial = sim.obter_dados()
        for _ in range(30):
            sim.atualizar(1 / 30)
        final = sim.obter_dados()
        sim.reiniciar()
        self.assertEqual(inicial, sim.obter_dados())
        for _ in range(30):
            sim.atualizar(1 / 30)
        self.assertEqual(final, sim.obter_dados())

    def test_cenarios_tem_alertas_coerentes(self):
        sim = SimuladorVoo()
        self.assertEqual(sim.obter_dados()["nivel_alerta"], 0)
        rng = sim._rng.getstate()
        sim.definir_cenario("trafego")
        dados = sim.obter_dados()
        self.assertEqual(dados["nivel_alerta"], 1)
        self.assertTrue(any(a["alerta"] for a in dados["tcas_alvos"]))
        sim.definir_cenario("incêndio")
        dados = sim.obter_dados()
        self.assertEqual(dados["cenario"], "incendio")
        self.assertEqual(dados["nivel_alerta"], 2)
        self.assertEqual(dados["focos_detectados"], 3)
        self.assertGreater(dados["temperatura_foco"], 300)
        sim.definir_cenario("normal")
        self.assertEqual(sim.obter_dados()["mensagens_alerta"], [])
        self.assertEqual(rng, sim._rng.getstate())
        with self.assertRaises(ValueError):
            sim.definir_cenario("inexistente")

    def test_dados_sao_copias_e_rng_global_preservado(self):
        estado_global = random.getstate()
        sim = SimuladorVoo()
        dados = sim.obter_dados()
        dados["tcas_alvos"][0]["x"] = 999
        dados["trajetoria_pontos"].clear()
        dados["mensagens_alerta"].append("INJETADO")
        sim.atualizar(0.1)
        self.assertNotEqual(sim.obter_dados()["tcas_alvos"][0]["x"], 999)
        self.assertEqual(len(sim.obter_dados()["trajetoria_pontos"]), 5)
        self.assertNotIn("INJETADO", sim.obter_dados()["mensagens_alerta"])
        self.assertEqual(estado_global, random.getstate())

    def test_passo_explicito_nao_truncado_e_validacao(self):
        sim = SimuladorVoo()
        sim.atualizar(1.5)
        self.assertEqual(sim.obter_dados()["tempo"], 1.5)
        for dt in (-1, float("inf"), float("nan")):
            with self.assertRaises(ValueError):
                sim.atualizar(dt)

    def test_relogio_monotonico(self):
        with patch("simulador.time.perf_counter", side_effect=[100.0, 100.25]):
            sim = SimuladorVoo()
            sim.atualizar()
        self.assertEqual(sim.obter_dados()["tempo"], 0.25)


if __name__ == "__main__":
    unittest.main()
