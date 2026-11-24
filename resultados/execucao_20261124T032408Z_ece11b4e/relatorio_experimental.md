# Relatório experimental de composição gráfica

## Método

Latência CPU + GPU em framebuffer offscreen RGBA8. Cada quadro inclui construção da geometria, envio dos comandos e `ctx.finish()`; não inclui simulação, coleta de recursos, PNG, eventos, troca de buffers ou V-Sync. Não corresponde ao tempo exclusivo da GPU nem à latência de apresentação na tela.

Aquecimento por execução: 60 quadros; coleta por repetição: 180 quadros; repetições: 6; semente: 42. As estratégias recebem os mesmos snapshots com passo fixo de 1/60 s. A ordem alterna entre repetições.

Cenário: incendio; cena 3D: 6000 gaussianas. A contagem de gaussianas é independente da carga sintética de retângulos dos presets.

FPS é 1000 dividido pela média dos tempos. Percentis usam interpolação linear. Os agregados reúnem todas as amostras; o CSV por repetição permite examinar a variação entre execuções. As barras de erro mostram o desvio padrão entre médias das repetições, não um intervalo de confiança.

CPU é a razão entre segundos de CPU do processo e tempo de parede de toda a coleta; pode exceder 100% em vários núcleos. O arquivo de recursos traz RSS amostrada e CPU em intervalos de pelo menos 100 ms quando disponíveis. RSS mede o processo completo, incluindo Python e caches do driver; não mede VRAM ou memória exclusiva de uma estratégia.

## Resultados agregados

| Config | Estratégia | Repetições | Quadros | Média (ms) | P95 (ms) | P99 (ms) | Máximo observado (ms) | FPS | Fora de 16,67 ms |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| C2 | Monolítica | 6 | 1080 | 6.976 | 10.106 | 14.133 | 15.597 | 143.35 | 0.00% |
| C2 | Multicamada | 6 | 1080 | 7.113 | 11.926 | 14.541 | 17.458 | 140.59 | 0.09% |
| C4 | Multicamada | 6 | 1080 | 16.878 | 18.698 | 24.658 | 30.518 | 59.25 | 45.74% |
| C4 | Monolítica | 6 | 1080 | 16.821 | 19.257 | 23.786 | 29.561 | 59.45 | 36.85% |

## Comparação observada

- **C2:** média multicamada 1.96% maior que a monolítica; P99 observado de 14.541 ms contra 14.133 ms. Quadros acima do orçamento: 0.09% contra 0.00%.
- **C4:** média multicamada 0.34% maior que a monolítica; P99 observado de 24.658 ms contra 23.786 ms. Quadros acima do orçamento: 45.74% contra 36.85%.

## Limites da interpretação

Os números descrevem somente a carga, o ambiente e a duração registrados. P95, P99 e máximo observado não são WCET nem garantias de prazo; zero violações observadas não assegura ausência futura. A separação em camadas, por si só, não demonstra melhor previsibilidade. Não foram avaliados escalonamento de tempo real, tolerância a falhas ou certificação aeronáutica. O aplicativo é uma demonstração acadêmica.

Os testes usam a mesma sessão de processo/contexto, liberando recursos entre execuções; caches do driver, temperatura, frequência da GPU e atividade do sistema podem influenciar os resultados. Alternar a ordem reduz um possível viés, mas não substitui controle ambiental ou estudo estatístico de significância.

## Arquivos para auditoria

- `amostras_frames.csv`: uma linha por quadro, com configuração, estratégia e repetição.
- `amostras_recursos.csv`: RSS e intervalos de CPU medidos fora da duração do quadro.
- `resultados_benchmark.csv`: estatísticas de cada repetição; `resumo_agregado.csv`: agregados.
- `resumo.json` e `metadados.json`: parâmetros, versões e identificação do ambiente OpenGL.
- `graficos/`: FPS, médias, distribuição e recursos; `capturas/`: último quadro da primeira repetição.
