import re

from django import forms

from ordering.payments import DECLINE_CARD, EXAMPLE_CARD


class CheckoutForm(forms.Form):
    card_number = forms.CharField(
        label="Card number",
        max_length=25,
        help_text=(
            f"Test mode, no real payments. Any number is accepted except "
            f"{DECLINE_CARD}, which always declines. Example: {EXAMPLE_CARD}."
        ),
    )
    idempotency_key = forms.UUIDField(widget=forms.HiddenInput)

    def clean_card_number(self) -> str:
        digits = re.sub(r"\D", "", self.cleaned_data["card_number"])
        if not 13 <= len(digits) <= 19:
            raise forms.ValidationError("Enter a card number of 13 to 19 digits.")
        return digits
