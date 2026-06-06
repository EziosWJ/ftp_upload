gc_gx-ZUQ1oaoDxYs0qzQsogVg9oRR5BxJU

curl https://api.generalcompute.com/v1/chat/completions \
  -H "Authorization: Bearer gc_gx-ZUQ1oaoDxYs0qzQsogVg9oRR5BxJU" \
  -H "Content-Type: application/json" \
  -d '{
        "model": "minimax-m2.7",
        "messages": [
          {"role": "system", "content": "You are a helpful assistant."},
          {"role": "user", "content": "Summarize this paragraph"}
        ],
        "stream": false
      }'