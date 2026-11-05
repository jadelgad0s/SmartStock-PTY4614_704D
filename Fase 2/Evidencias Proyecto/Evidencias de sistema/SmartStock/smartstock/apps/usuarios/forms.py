from django import forms
from .models import Usuario, Rol

class UsuarioForm(forms.ModelForm):
    # Campo extra para la clave, ya que no se guarda en texto plano
    password = forms.CharField(widget=forms.PasswordInput(attrs={'class': 'form-control'}), required=False)

    class Meta:
        model = Usuario
        # Solo muestro los campos que el admin puede editar
        fields = ['email', 'rol', 'activo']
        widgets = {
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'rol': forms.Select(attrs={'class': 'form-select'}),
            'activo': forms.CheckboxInput(attrs={'class': 'form-check-input'})
        }

    def save(self, commit=True):
        # Capturo el usuario antes de guardarlo en la BD
        user = super().save(commit=False)
        # Si el admin escribió una clave, la encripto
        if self.cleaned_data.get('password'):
            user.set_password(self.cleaned_data['password'])
        if commit:
            user.save()
        return user