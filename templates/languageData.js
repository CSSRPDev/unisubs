var allLanguages = [ {% for code, name in languages %}"{{ code }}"{% if not forloop.last %},{% endif %}{% endfor %} ];
var popularLanguages = [{% for code in popular_languages %}"{{ code }}"{% if not forloop.last %},{% endif %}{% endfor %} ];
var languageNames = { {% for code, name in languages %}"{{ code }}": "{{ name }}"{% if not forloop.last %},{% endif %}{% endfor %} };

function getLanguageName(languageCode) {
    return languageNames[languageCode];
}
