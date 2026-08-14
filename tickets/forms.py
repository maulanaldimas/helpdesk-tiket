from django import forms
from django.contrib.auth.models import User
from .models import Ticket, Comment, Company, Category, Profile, Article

INPUT_CLASS = 'w-full border border-slate-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-orange-500 focus:border-transparent'
SELECT_CLASS = 'w-full border border-slate-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-orange-500'
FILE_CLASS = 'block w-full text-sm text-slate-500 file:mr-3 file:py-1.5 file:px-3 file:rounded-lg file:border-0 file:text-sm file:font-medium file:bg-indigo-50 file:text-indigo-600 hover:file:bg-indigo-100 transition'


class MultipleFileInput(forms.FileInput):
    allow_multiple_selected = True


class MultipleFileField(forms.FileField):
    """FileField yang menerima banyak file sekaligus dari widget multiple."""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault('widget', MultipleFileInput(attrs={'class': FILE_CLASS}))
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        if not data:
            return []
        if isinstance(data, (list, tuple)):
            return [super().clean(d, initial) for d in data]
        return [super().clean(data, initial)]


class TicketForm(forms.ModelForm):
    files = MultipleFileField(
        label='Lampiran',
        required=False,
        help_text='Pilih beberapa file sekaligus (screenshot, log, dokumen). Maks 10 MB per file.',
    )

    class Meta:
        model = Ticket
        fields = ['title', 'description', 'company', 'category', 'priority']
        widgets = {
            'title': forms.TextInput(attrs={'class': INPUT_CLASS}),
            'description': forms.Textarea(attrs={'rows': 4, 'class': INPUT_CLASS}),
            'company': forms.Select(attrs={'class': SELECT_CLASS}),
            'category': forms.Select(attrs={'class': SELECT_CLASS}),
            'priority': forms.Select(attrs={'class': SELECT_CLASS}),
        }


class CommentForm(forms.ModelForm):
    files = MultipleFileField(
        label='Lampiran',
        required=False,
        help_text='Maks 10 MB per file.',
    )

    class Meta:
        model = Comment
        fields = ['message']
        widgets = {
            'message': forms.Textarea(attrs={
                'rows': 3,
                'placeholder': 'Tulis komentar...',
                'class': INPUT_CLASS,
            }),
        }


class CompanyForm(forms.ModelForm):
    class Meta:
        model = Company
        fields = ['name']
        widgets = {
            'name': forms.TextInput(attrs={'class': INPUT_CLASS}),
        }


class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ['name', 'description']
        widgets = {
            'name': forms.TextInput(attrs={'class': INPUT_CLASS}),
            'description': forms.Textarea(attrs={'rows': 2, 'class': INPUT_CLASS}),
        }


class UserCreateForm(forms.ModelForm):
    password = forms.CharField(
        label='Password',
        widget=forms.PasswordInput(attrs={'class': INPUT_CLASS}),
        min_length=8,
        help_text='Minimal 8 karakter.',
    )
    role = forms.ChoiceField(label='Role', choices=Profile.ROLE_CHOICES, widget=forms.Select(attrs={'class': SELECT_CLASS}))
    company = forms.ModelChoiceField(
        label='Company',
        queryset=Company.objects.all(),
        required=False,
        widget=forms.Select(attrs={'class': SELECT_CLASS}),
    )

    class Meta:
        model = User
        fields = ['username', 'first_name', 'email']
        widgets = {
            'username': forms.TextInput(attrs={'class': INPUT_CLASS}),
            'first_name': forms.TextInput(attrs={'class': INPUT_CLASS}),
            'email': forms.EmailInput(attrs={'class': INPUT_CLASS}),
        }

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data['password'])
        user.is_active = True
        if commit:
            user.save()
            profile, _ = Profile.objects.get_or_create(user=user)
            profile.role = self.cleaned_data['role']
            profile.company = self.cleaned_data['company']
            profile.save()
        return user


class UserEditForm(forms.ModelForm):
    role = forms.ChoiceField(label='Role', choices=Profile.ROLE_CHOICES, widget=forms.Select(attrs={'class': SELECT_CLASS}))
    company = forms.ModelChoiceField(
        label='Company',
        queryset=Company.objects.all(),
        required=False,
        widget=forms.Select(attrs={'class': SELECT_CLASS}),
    )

    class Meta:
        model = User
        fields = ['username', 'first_name', 'last_name', 'email', 'is_active']
        widgets = {
            'username': forms.TextInput(attrs={'class': INPUT_CLASS}),
            'first_name': forms.TextInput(attrs={'class': INPUT_CLASS}),
            'last_name': forms.TextInput(attrs={'class': INPUT_CLASS}),
            'email': forms.EmailInput(attrs={'class': INPUT_CLASS}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk and hasattr(self.instance, 'profile'):
            self.fields['role'].initial = self.instance.profile.role
            self.fields['company'].initial = self.instance.profile.company_id

    def save(self, commit=True):
        user = super().save(commit=commit)
        if user.pk:
            profile, _ = Profile.objects.get_or_create(user=user)
            profile.role = self.cleaned_data['role']
            profile.company = self.cleaned_data['company']
            profile.save()
        return user


class RegistrationForm(forms.Form):
    """Form pendaftaran mandiri; akun dibuat nonaktif sampai disetujui admin."""
    username = forms.CharField(label='Username', max_length=150, widget=forms.TextInput(attrs={'class': INPUT_CLASS}))
    first_name = forms.CharField(label='Nama Lengkap', max_length=150, widget=forms.TextInput(attrs={'class': INPUT_CLASS}))
    email = forms.EmailField(label='Email', widget=forms.EmailInput(attrs={'class': INPUT_CLASS}))
    company = forms.ModelChoiceField(
        label='Company',
        queryset=Company.objects.all(),
        widget=forms.Select(attrs={'class': SELECT_CLASS}),
    )
    password1 = forms.CharField(
        label='Password',
        widget=forms.PasswordInput(attrs={'class': INPUT_CLASS}),
        min_length=8,
        help_text='Minimal 8 karakter.',
    )
    password2 = forms.CharField(
        label='Konfirmasi Password',
        widget=forms.PasswordInput(attrs={'class': INPUT_CLASS}),
    )

    def clean_username(self):
        username = self.cleaned_data['username']
        if User.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError('Username sudah dipakai.')
        return username

    def clean_email(self):
        email = self.cleaned_data['email'].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError('Email sudah terdaftar.')
        return email

    def clean_password2(self):
        p1 = self.cleaned_data.get('password1')
        p2 = self.cleaned_data.get('password2')
        if p1 and p2 and p1 != p2:
            raise forms.ValidationError('Password tidak cocok.')
        return p2


class ArticleForm(forms.ModelForm):
    class Meta:
        model = Article
        fields = ['title', 'category', 'content', 'is_published']
        widgets = {
            'title': forms.TextInput(attrs={'class': INPUT_CLASS}),
            'category': forms.Select(attrs={'class': SELECT_CLASS}),
            'content': forms.Textarea(attrs={'rows': 12, 'class': INPUT_CLASS}),
            'is_published': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-slate-300 text-orange-500'}),
        }
