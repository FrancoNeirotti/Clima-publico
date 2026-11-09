otras() {
  gh run list -R "$GITHUB_REPOSITORY" --workflow datos.yml --limit 30 \
    --json databaseId,status \
    --jq "[.[] | select(.databaseId < $GITHUB_RUN_ID and .status != \"completed\")] | length"
}
espera=0
[ "$GITHUB_EVENT_NAME" = "workflow_dispatch" ] && espera=900
inicio=$(date +%s)
while n=$(otras) && [ "$n" -gt 0 ]; do
  if [ $(( $(date +%s) - inicio )) -ge "$espera" ]; then
    echo "Ya hay $n corrida(s) activa(s); esta termina sin hacer nada."
    echo "seguir=false" >> "$GITHUB_OUTPUT"
    exit 0
  fi
  echo "Esperando a que termine la corrida anterior..."
  sleep 20
done
echo "seguir=true" >> "$GITHUB_OUTPUT"
