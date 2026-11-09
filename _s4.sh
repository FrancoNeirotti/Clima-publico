publicar() {
  # Encadenado con && porque dentro de un "if" bash no corta ante errores.
  rm -rf publicar && mkdir publicar &&
  cp -r cache publicar/cache &&
  cp salida/estaciones.json publicar/ &&
  cd publicar &&
  git init -q -b datos &&
  git config user.name "github-actions[bot]" &&
  git config user.email "41898282+github-actions[bot]@users.noreply.github.com" &&
  git add -A &&
  git commit -q -m "Datos $(date -u +%Y-%m-%dT%H:%MZ)" &&
  git push -q -f "https://x-access-token:${GITHUB_TOKEN}@github.com/${GITHUB_REPOSITORY}.git" datos
  local estado=$?
  cd "$GITHUB_WORKSPACE"
  return $estado
}
fin=$(( $(date +%s) + 330 * 60 ))
vuelta=0
while true; do
  inicio=$(date +%s)
  vuelta=$((vuelta + 1))
  echo "::group::Vuelta $vuelta ($(date -u +%H:%M:%SZ))"
  if python servidor.py --generar salida --limite 480 && publicar; then
    echo "Publicado."
  else
    echo "::warning::La vuelta $vuelta falló; se reintenta en la próxima."
  fi
  echo "::endgroup::"
  proxima=$(( inicio + 300 ))
  [ "$proxima" -ge "$fin" ] && break
  resto=$(( proxima - $(date +%s) ))
  [ "$resto" -gt 0 ] && sleep "$resto"
done
