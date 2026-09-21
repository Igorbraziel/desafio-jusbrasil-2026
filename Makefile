# Desafio Jusbrasil x BRACIS 2026 — atalhos do fluxo de trabalho.
# Ordem típica:  make dados -> make indice -> make testar -> make rodar -> make avaliar

ZIP  ?= data/raw/desafio-jusbrasil-bracis-2026.zip
DEV  ?= data/dev
OUT  ?= data/out
RUN  := uv run

.PHONY: ajuda dados dados-zip indice testar lint rodar avaliar solution submissao requirements docker limpar

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

submissao: rodar ## Gera data/submission.csv para enviar no Kaggle
	$(RUN) python $(DEV)/ferramentas/json_to_submission.py $(OUT) data/submission.csv

requirements: ## Exporta requirements.txt pinado para o Dockerfile
	uv export --no-dev --format requirements-txt --no-emit-project > requirements.txt

docker: requirements ## Constrói a imagem de submissão
	docker build -t verificador-citacoes:latest .

limpar: ## Remove saídas geradas
	rm -rf $(OUT) .pytest_cache .ruff_cache
