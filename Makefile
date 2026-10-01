# Desafio Jusbrasil x BRACIS 2026 — atalhos do fluxo de trabalho.
# Ordem típica:  make dados -> make indice -> make testar -> make rodar -> make avaliar

ZIP  ?= data/raw/desafio-jusbrasil-bracis-2026.zip
DEV  ?= data/dev
OUT  ?= data/out
RUN  := uv run

.PHONY: ajuda dados dados-zip indice testar lint rodar avaliar solution submissao \
        entrega baseline robustez confianca requirements docker limpar

ajuda:
	@grep -E '^[a-z-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

dados: ## Baixa a distribuição final da aba Data do Kaggle (exige credencial própria)
	$(RUN) --with kagglehub python scripts/baixar_dados.py --destino $(DEV)

dados-zip: ## Aplica um zip já baixado à mão da aba Data (ZIP=caminho)
	$(RUN) python scripts/baixar_dados.py --zip $(ZIP) --destino $(DEV)

indice: ## Constrói o índice de cabeçalhos dos acórdãos (offline, uma vez)
	$(RUN) python scripts/construir_indice.py --db $(DEV)/desafio1_bracis.db --saida $(DEV)/indice_cabecalhos.json

testar: ## Roda a suíte de testes
	$(RUN) pytest -q

lint: ## Checa estilo e imports
	$(RUN) ruff check . && $(RUN) ruff format --check .

rodar: ## Gera um JSON por documento em data/out/
	$(RUN) python -m verificador.cli --input $(DEV)/txt --output $(OUT) --db $(DEV)/desafio1_bracis.db

avaliar: ## Pontua data/out/ pela métrica OFICIAL do Kaggle
	$(RUN) python scripts/avaliar.py --predicoes $(OUT) --goldenset $(DEV)/goldenset.csv

solution: ## Converte o goldenset no solution.csv da métrica oficial
	$(RUN) python scripts/construir_solution.py --goldenset $(DEV)/goldenset.csv --saida $(DEV)/solution.csv

baseline: rodar ## Grava o score limpo em data/dev/baseline.json (referência do arnês)
	$(RUN) python scripts/avaliar.py --predicoes $(OUT) --goldenset $(DEV)/goldenset.csv --baseline $(DEV)/baseline.json

robustez: ## Mede a degradação por classe de ruído (exige `make baseline`)
	$(RUN) python scripts/medir_robustez.py --taxa 0.15 --sementes 3

confianca: ## Mede a acurácia por caminho de decisão, para calibrar CONFIANCA
	$(RUN) python scripts/medir_confianca.py --taxa 0.15 --sementes 3

# O CSV sai do nosso escritor (verificador.submissao), que reproduz byte a byte
# o conversor da organização — sem depender de data/dev/ferramentas para gerar.
submissao: ## Gera e confere data/submission.csv para enviar no Kaggle
	$(RUN) python -m verificador.cli --input $(DEV)/txt --output $(OUT) --csv data/submission.csv --db $(DEV)/desafio1_bracis.db
	$(RUN) python scripts/conferir_submissao.py data/submission.csv $(DEV)/sample_submission.csv

# O que a avaliação final roda — o run.sh sobre a base e os pareceres —, pontuado
# pela métrica oficial direto do CSV entregue.
entrega: ## Roda o run.sh da entrega no dev e pontua o CSV pela métrica oficial
	bash run.sh $(DEV)/desafio1_bracis.db $(DEV)/txt data/submission.csv $(OUT)
	$(RUN) python scripts/avaliar.py --submissao data/submission.csv --goldenset $(DEV)/goldenset.csv

requirements: ## Exporta requirements.txt pinado para o Dockerfile
	uv export --no-dev --format requirements-txt --no-emit-project > requirements.txt

# Sem depender de `requirements`: o requirements.txt é versionado, e exportá-lo
# exigiria uv no host só para construir a imagem.
docker: ## Constrói a imagem da entrega
	docker build -t verificador-citacoes:latest .

limpar: ## Remove saídas geradas
	rm -rf $(OUT) .pytest_cache .ruff_cache
