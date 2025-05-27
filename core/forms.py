from django import forms
from .models import UserFile, AIModel
from django.core.validators import FileExtensionValidator

class DockerfileUploadForm(forms.Form):
    dockerfile = forms.FileField(
        label="Upload Dockerfile",
        widget=forms.FileInput(attrs={
            'class': 'form-control',
            'accept': '.dockerfile,Dockerfile'
        }),
        help_text="Upload your Dockerfile to build a custom container"
    )

    def clean_dockerfile(self):
        dockerfile = self.cleaned_data.get('dockerfile')
        if dockerfile:
            if not dockerfile.name.lower().endswith(('dockerfile', '.dockerfile')):
                raise forms.ValidationError("Only Dockerfile files are allowed")
        return dockerfile


class DockerImageForm(forms.Form):
    image_name = forms.CharField(
        label='Docker Image',
        help_text='e.g., nginx:latest or python:3.9-slim',
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter official Docker image name'
        })
    )


class FileUploadForm(forms.ModelForm):
    class Meta:
        model = UserFile
        fields = ['file']
        widgets = {
            'file': forms.FileInput(attrs={
                'class': 'form-control',
                'multiple': False
            })
        }
        help_texts = {
            'file': 'Maximum file size: 100MB'
        }

    def clean_file(self):
        file = self.cleaned_data.get('file')
        if file and file.size > 100 * 1024 * 1024:  # 100MB
            raise forms.ValidationError("File size exceeds 100MB limit")
        return file


class AIModelForm(forms.ModelForm):
    class Meta:
        model = AIModel
        fields = ['name', 'model_file', 'framework']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Model name'
            }),
            'model_file': forms.FileInput(attrs={
                'class': 'form-control',
                'accept': '.h5,.pt,.onnx,.pb,.pkl'
            }),
            'framework': forms.Select(attrs={
                'class': 'form-control'
            }),
        }
        help_texts = {
            'model_file': 'Supported formats: .h5 (Keras/TF), .pt (PyTorch), .onnx, .pb, .pkl',
            'framework': 'Select the framework this model was trained with'
        }

    def clean_model_file(self):
        model_file = self.cleaned_data.get('model_file')
        valid_extensions = ['.h5', '.pt', '.onnx', '.pb', '.pkl']
        if model_file:
            if not any(model_file.name.lower().endswith(ext) for ext in valid_extensions):
                raise forms.ValidationError(
                    "Unsupported file format. Supported formats: " + ", ".join(valid_extensions)
                )
            if model_file.size > 500 * 1024 * 1024:  # 500MB
                raise forms.ValidationError("Model file exceeds 500MB size limit")
        return model_file


class ContainerActionForm(forms.Form):
    ACTION_CHOICES = [
        ('start', 'Start Container'),
        ('stop', 'Stop Container'),
        ('delete', 'Delete Container'),
    ]
    action = forms.ChoiceField(
        choices=ACTION_CHOICES,
        widget=forms.RadioSelect(attrs={'class': 'form-check-input'})
    )
