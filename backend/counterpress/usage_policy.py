"""Product usage policy; accounting and concurrency remain enabled."""
import os


def usage_caps_enabled():
    # Owner approved removing app spend/hour/day ceilings for judging (27 Oct).
    # Operators may explicitly restore the previous policy without losing charges.
    return os.environ.get('COUNTERPRESS_USAGE_CAPS', 'off') != 'off'
