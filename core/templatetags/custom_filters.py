from django import template

register = template.Library()

@register.filter
def spilt(value, delimiter):
    return value.split(delimiter)