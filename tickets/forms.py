from django import forms
from django.contrib.auth.models import User
from .models import Ticket, Comment, Company, Category, Profile, Article

INPUT_CLASS = 'w-full border border-slate-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-orange-500 focus:border-transparent'
SELECT_CLASS = 'w-full border border-slate-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-orange-500'


class TicketForm(forms.ModelForm):
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
