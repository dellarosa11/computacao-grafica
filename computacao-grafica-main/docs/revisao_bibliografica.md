# Revisão bibliográfica e posicionamento do protótipo

O AERIS investiga uma questão delimitada: como a composição por camadas altera o custo de uma visualização interativa que combina uma cena tridimensional e instrumentos transparentes? A aplicação representa uma estação de monitoramento de drone em uma missão sintética de reconhecimento de incêndios. Essa adaptação mantém o tema aeronáutico e permite explorar integração visual, sem apresentar o programa como equipamento de voo.

## Composição em sistemas aviônicos

Barladian et al. (2019), em [*Multi-windows Rendering Using Software OpenGL in Avionics Embedded Systems*](https://ceur-ws.org/Vol-2485/paper7.pdf), descrevem um compositor de imagens para OpenGL SC 1.0.1 e JetOS. Aplicações produzem buffers fora da tela, posteriormente reunidos para exibição. O trabalho discute sincronização, particionamento e alternativas com múltiplos núcleos. A contribuição relevante para este projeto é a separação entre produção de conteúdo e composição final; seus resultados de desempenho pertencem à plataforma e à configuração estudadas pelos autores.

## GPU e garantia de software

Trompouki e Kosmidis (2021), em [*DO-178C Certification of General-Purpose GPU Software: Review of Existing Methods and Future Directions*](https://upcommons.upc.edu/entities/publication/cba59e9b-e05d-448a-bf05-476fd0573b86), revisam métodos de certificação de software de aplicação executado em GPU, explicitando premissas relacionadas ao compilador. Essa revisão situa o uso de aceleradores em um processo de verificação mais amplo. O artigo não constitui uma certificação genérica de bibliotecas gráficas. DOI: [10.1109/DASC52595.2021.9594412](https://doi.org/10.1109/DASC52595.2021.9594412).

## Representação por Gaussianas

Kerbl et al. (2023), em [*3D Gaussian Splatting for Real-Time Radiance Field Rendering*](https://repo-sam.inria.fr/fungraph/3d-gaussian-splatting/), propõem uma representação por Gaussianas tridimensionais, otimização com controle de densidade e renderização que considera visibilidade. O método parte de pontos associados à calibração de câmeras e busca sintetizar novas vistas de cenas capturadas. Essa referência fundamenta a escolha de primitivas volumétricas anisotrópicas projetadas na imagem. DOI: [10.1145/3592433](https://doi.org/10.1145/3592433).

## Aplicação crítica ao AERIS

Neste protótipo, cada grupo funcional pode ocupar um FBO RGBA8. Todos compartilham processo, contexto OpenGL e recursos da GPU. A separação de imagens oferece organização e controle de visibilidade, mas não implementa isolamento temporal ou espacial ARINC 653, contenção de falhas ou certificação. ModernGL e OpenGL convencional atendem à demonstração acadêmica proposta.

O terreno, o fogo e a fumaça são construídos proceduralmente, com posições, covariâncias e cores definidas pelo gerador. Há projeção perspectiva, transformação das covariâncias, descarte e ordenação dos splats. Não há treinamento de campo de radiância, reconstrução de fotografias, otimização de densidade ou harmônicos esféricos. Portanto, a implementação demonstra uma adaptação dos princípios de splatting, sem reproduzir integralmente o sistema de Kerbl et al.

A avaliação mantém dados, resolução, ordem e transparência equivalentes entre estratégias. Tempos incluem trabalho da CPU e conclusão da GPU; percentis e máximos descrevem as amostras coletadas, sem estabelecer WCET. A contribuição é um experimento reproduzível com limites explícitos, cuja interpretação depende do hardware e das cargas efetivamente medidas.
