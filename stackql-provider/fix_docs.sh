find website/docs/services -type f -name "*.md" -exec sed -i \
  -e 's/<table><tbody>/<table>\n<tbody>/g' \
  -e 's#</tbody></table>#</tbody>\n</table>#g' {} +

find website/docs/services -type f -name "*.md" -exec sed -i \
  -e 's#<tbody><tr>#<tbody>\n<tr>#g' {} +

find website/docs/services -type f -name "*.md" -exec sed -i \
  -e 's/\*/&#42;/g' {} +

