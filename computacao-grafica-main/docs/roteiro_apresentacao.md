# Roteiro de apresentação — aproximadamente cinco minutos

Antes de iniciar, execute `python main.py`. Deixe o cenário de incêndio selecionado, a carga sintética desligada e a janela visível. Mantenha o relatório experimental gerado pelo benchmark disponível para a etapa de resultados.

## 0:00–0:35 — Problema e objetivo

“O AERIS é uma estação acadêmica de monitoramento aéreo. A missão sintética combina terreno, focos de incêndio, navegação e instrumentos. Investigamos o custo de reunir essas informações por duas estratégias de composição gráfica.”

Aponte os painéis de missão, navegação e sistemas. Explique que os dados e os alertas são simulados, sem conexão com aeronave ou sensor real.

## 0:35–1:25 — Gaussianas e interação

Arraste com o botão esquerdo sobre o terreno para orbitar. Use a roda do mouse para aproximar ou afastar; pressione **Home** para restaurar a câmera.

“O volume é representado por Gaussianas 3D. Projetamos seus centros e covariâncias na câmera, descartamos splats invisíveis e os desenhamos do fundo para a frente. A transparência dá continuidade ao terreno e permite representar fumaça.”

Esclareça que a cena é procedural: não foi treinada com fotografias. Pressione **I** para demonstrar a simbologia sobreposta e volte ao estado anterior.

## 1:25–2:20 — Composição e camadas

Pressione **Espaço** para pausar e **M** para alternar monolítica/multicamada. Use **F1–F4** para ocultar e restaurar grupos. Pressione **C** para comparar dois e quatro grupos físicos; restaure quatro.

“No modo monolítico, as funções desenham diretamente no mesmo destino. No multicamada, cada grupo desenha em uma textura intermediária, depois combinada no quadro final. Ambos preservam a ordem do conteúdo. O alfa pré-multiplicado evita aplicar transparência duas vezes.”

## 2:20–3:10 — Cenários e carga

Retome com **Espaço**. Pressione **N** para percorrer normal, tráfego e incêndio; mostre a mudança dos alertas. Use **1** para aplicar C1, **S** para alternar a carga e **T** para alterar sua proporção transparente. Evite carregar C4 durante a fala se o computador perder fluidez. **G** alterna a cena 3D e o horizonte; restaure a cena.

## 3:10–4:20 — Experimento e resultados

Abra o relatório experimental e apresente os números efetivamente obtidos. Explique os presets, o aquecimento, as repetições e o uso dos mesmos dados nas duas estratégias. Compare tempo médio, P95/P99, dispersão e memória; indique as amostras acima de 16,67 ms quando presentes.

“O benchmark mede construção e envio pela CPU mais a espera pela conclusão da GPU. Não é tempo exclusivo da GPU nem inclui apresentação na tela. O maior valor observado não é WCET. O FPS do painel interativo também depende de V-Sync e apresentação, por isso não substitui o experimento.”

## 4:20–5:00 — Contribuição e limites

“Entregamos duas estratégias comparáveis, uma cena 3D interativa, testes numéricos e visuais e resultados auditáveis. A composição por FBO organiza imagens, mas não fornece particionamento ARINC 653 nem certificação aeronáutica. As conclusões de desempenho valem para a máquina e as cargas medidas.”

Volte à aplicação e pressione **P** para salvar uma captura com metadados. **H** abre a ajuda; **Esc** fecha a ajuda ou encerra o programa. Se a demonstração ao vivo falhar, use a captura e os resultados já gerados.
