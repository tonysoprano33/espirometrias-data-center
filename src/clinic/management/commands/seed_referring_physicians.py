from django.core.management.base import BaseCommand

from clinic.models import ReferringPhysician


RAW_PHYSICIAN_NAMES = [
    "ABREGU, Vanina",
    "ADLER, Israel",
    "ALDECO, Guillermo",
    "CORBO, Alfredo E.",
    "BALBUENA, Enzo Hernan",
    "BARBIERI, Gustavo",
    "BASTIANELLI, Gustavo",
    "BECERRA, Rosa Amelia",
    "BONGIOVANNI, Raul Ricardo",
    "BOTTELLO, Ruben",
    "DANDREA, Gustavo",
    "DOMENICONI, Javier",
    "FAJARDO, Ana Cristina",
    "FERNANDEZ MOSRE, Maria Ines",
    "GIANNOBOLI, Valeria",
    "GAVILAN, Pablo M.",
    "JAIME, Ines",
    "LEGUIZA, Guillermo",
    "LUCERO, Emilio",
    "MARRACO, Guillermo",
    "MURACCIOLE, Julio",
    "MERIGO, Sergio",
    "MURACT, Dario",
    "NAVARRO de la Fuente",
    "OLAGARAY, Lucas",
    "OLMOS, Juan Pablo",
    "OMELANCZUCK, Pablo E.",
    "OSSANA, Cesar",
    "OTTO HERZIG, Javier",
    "PEREZ ARANA, Enrique G.",
    "PESSOT, Sergio",
    "REYNA CORVALAN, Juan Carlos",
    "RODRIGUEZ, Franco",
    "RODRIGUEZ, Teresa",
    "RODRIGUEZ, Miguel A.",
    "RODRIGUEZ CANOSA, Jhon",
    "SANZOZ, Gaston",
    "VILLAR, Marcela",
    "GIANNOBILI, Valeria",
    "FAJARDO, Ana",
    "VERDECEFRIA, Mariana",
    "JOFRE, Cristian Adrian",
    "POLINI",
    "HERZING, Javier",
    "SANCHES, Rene",
]


LOWERCASE_PARTICLES = {"de", "del", "la", "las", "los", "y"}


def titlecase_name(value):
    words = []
    for word in str(value or "").strip().split():
        lowered = word.lower()
        if lowered in LOWERCASE_PARTICLES:
            words.append(lowered)
        else:
            words.append("-".join(part.capitalize() for part in lowered.split("-")))
    return " ".join(words)


def normalize_physician_name(raw_name):
    raw_name = " ".join(str(raw_name or "").replace(".", " ").split()).strip(" ,")
    if not raw_name:
        return ""
    raw_name = raw_name.removeprefix("DRA ").removeprefix("DR ")

    if "," in raw_name:
        last_name, first_name = [part.strip() for part in raw_name.split(",", 1)]
        normalized = f"{titlecase_name(last_name)}, {titlecase_name(first_name)}"
    else:
        normalized = titlecase_name(raw_name)

    return f"DR. {normalized}"


class Command(BaseCommand):
    help = "Carga la lista base de medicos derivantes."

    def handle(self, *args, **options):
        created = 0
        updated = 0
        for raw_name in RAW_PHYSICIAN_NAMES:
            full_name = normalize_physician_name(raw_name)
            if not full_name:
                continue
            physician, was_created = ReferringPhysician.objects.get_or_create(
                full_name=full_name,
                defaults={"active": True},
            )
            if was_created:
                created += 1
                continue
            if not physician.active:
                physician.active = True
                physician.save(update_fields=["active", "updated_at"])
                updated += 1

        self.stdout.write(
            self.style.SUCCESS(f"Doctores cargados. Nuevos: {created}. Reactivados: {updated}.")
        )
