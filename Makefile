# Desafio Jusbrasil x BRACIS 2026 — atalhos do fluxo de trabalho.
# Ordem típica:  make dados -> make indice -> make testar -> make rodar -> make avaliar

ZIP  ?= data/raw/dados_desafio_jusbrasil.zip
DEV  ?= data/dev
OUT  ?= data/out
RUN  := uv run

.PHONY: ajuda dados dados-kaggle indice testar lint rodar avaliar submissao requirements docker limpar

ajuda:
	@grep -E '^[a-z-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

dados-kaggle: ## Baixa os arquivos da competição no Kaggle direto para data/dev/
	$(RUN) --with kagglehub python scripts/baixar_dados.py --destino $(DEV)

dados: ## (legado) Descompacta o zip do e-mail e gera data/dev/goldenset.csv do xlsx
	$(RUN) python scripts/preparar_dados.py --zip $(ZIP) --destino $(DEV)

indice: ## Constrói o índice de cabeçalhos dos acórdãos (offline, uma vez)
	$(RUN) python scripts/construir_indice.py --db $(DEV)/desafio1_bracis.db --saida $(DEV)/indice_cabecalhos.json

testar: ## Roda a suíte de testes
	$(RUN) pytest -q

lint: ## Checa estilo e imports
	$(RUN) ruff check . && $(RUN) ruff format --check .

rodar: ## Gera um JSON por documento em data/out/
	$(RUN) python -m verificador.cli --input $(DEV)/txt --output $(OUT) --db $(DEV)/desafio1_bracis.db

avaliar: ## Pontua data/out/ contra o goldenset (métrica local, provisória)
	$(RUN) python scripts/avaliar.py --predicoes $(OUT) --goldenset $(DEV)/goldenset.csv

submissao: rodar ## Empacota data/out/ no .zip de submissão ao leaderboard
	cd $(OUT) && zip -q -r ../submissao.zip *.json
	@echo "data/submissao.zip pronto ($$(ls $(OUT)/*.json | wc -l) documentos)"

requirements: ## Exporta requirements.txt pinado para o Dockerfile
	uv export --no-dev --format requirements-txt --no-emit-project > requirements.txt

docker: requirements ## Constrói a imagem de submissão
	docker build -t verificador-citacoes:latest .

limpar: ## Remove saídas geradas
	rm -rf $(OUT) .pytest_cache .ruff_cache
