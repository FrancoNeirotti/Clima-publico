if git fetch --depth=1 origin datos; then
  git archive FETCH_HEAD cache | tar -x || true
fi
